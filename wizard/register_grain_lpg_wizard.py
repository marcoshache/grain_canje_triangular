# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RegisterGrainLpgWizard(models.TransientModel):
    _name = "register.grain.lpg.wizard"
    _description = "Registrar LPG"

    date = fields.Date(required=True, default=fields.Date.context_today)

    # Datos AFIP-ish
    coe = fields.Char(string="C.O.E.")
    delivery_date = fields.Date(string="Fecha entrega")
    broker_id = fields.Many2one("res.partner", string="Corredor")
    port = fields.Char(string="Puerto")
    grain_grade = fields.Char(string="Grado")

    producer_id = fields.Many2one(
        "res.partner",
        string="Vendedor (Productor/Proveedor de grano)",
        required=True,
        domain="[('supplier_rank','>',0)]",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto servicio (Grano - Liquidación)",
        required=True,
        domain="[('detailed_type','=','service')]",
    )

    # Captura como en LPG: KG + Precio/KG (con precisión)
    qty_kg = fields.Float(string="Cantidad (Kg)", required=True, digits=(16, 2))
    price_per_kg = fields.Float(string="Precio por Kg", required=True, digits=(16, 4))

    qty_tn = fields.Float(string="Toneladas", compute="_compute_tn", store=True, readonly=True, digits=(16, 6))
    price_per_tn = fields.Monetary(
        string="Precio por TN", compute="_compute_price_tn", store=True, readonly=True,
        currency_field="currency_id"
    )

    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    amount_untaxed = fields.Monetary(string="Subtotal", compute="_compute_amounts", store=True, currency_field="currency_id")
    amount_tax = fields.Monetary(string="IVA", compute="_compute_amounts", store=True, currency_field="currency_id")
    amount_total = fields.Monetary(string="Total", compute="_compute_amounts", store=True, currency_field="currency_id")

    clearing_account_id = fields.Many2one(
        "account.account",
        string="Cuenta puente",
        default=lambda self: self.env.company.grain_clearing_account_id.id,
        required=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Diario Liquidaciones",
        default=lambda self: self.env.company.grain_liquidation_journal_id.id,
        required=True,
    )

    tax_id = fields.Many2one(
        "account.tax",
        string="IVA (compra)",
        domain="[('type_tax_use','=','purchase')]",
        default=lambda self: self.env.company.grain_lpg_tax_id.id,
    )

    @api.depends("qty_kg")
    def _compute_tn(self):
        for w in self:
            w.qty_tn = (w.qty_kg or 0.0) / 1000.0

    @api.depends("price_per_kg")
    def _compute_price_tn(self):
        for w in self:
            w.price_per_tn = (w.price_per_kg or 0.0) * 1000.0

    @api.depends("qty_kg", "price_per_kg", "tax_id", "currency_id")
    def _compute_amounts(self):
        for w in self:
            base = (w.qty_kg or 0.0) * (w.price_per_kg or 0.0)
            w.amount_untaxed = base
            w.amount_tax = 0.0
            w.amount_total = base
            if w.tax_id:
                taxes = w.tax_id.compute_all(
                    base, currency=w.currency_id, quantity=1.0,
                    product=False, partner=w.producer_id
                )
                w.amount_tax = taxes["total_included"] - taxes["total_excluded"]
                w.amount_total = taxes["total_included"]

    def action_create_lpg(self):
        self.ensure_one()

        if self.qty_kg <= 0 or self.price_per_kg <= 0:
            raise UserError(_("Cantidad y precio deben ser mayores a 0."))

        if not self.clearing_account_id:
            raise UserError(_("Falta la Cuenta puente (Granos a liquidar / Canje)."))
        if not self.journal_id:
            raise UserError(_("Falta el Diario de Liquidaciones de Granos."))

        liquidation = self.env["grain.liquidation"].create({
            "date": self.date,
            "producer_id": self.producer_id.id,
            "product_id": self.product_id.id,
            "qty_tn": self.qty_tn,
            "price_per_tn": self.price_per_tn,
            "clearing_account_id": self.clearing_account_id.id,
            "journal_id": self.journal_id.id,

            "coe": self.coe,
            "delivery_date": self.delivery_date,
            "broker_id": self.broker_id.id,
            "port": self.port,
            "grain_grade": self.grain_grade,
            "tax_id": self.tax_id.id,
        })

        line_vals = {
            "product_id": self.product_id.id,
            "name": self.product_id.display_name or "LPG",
            "quantity": self.qty_tn or 1.0,
            "price_unit": self.price_per_tn or self.amount_total,
            "account_id": self.clearing_account_id.id,
        }
        if self.tax_id:
            line_vals["tax_ids"] = [(6, 0, [self.tax_id.id])]

        bill_vals = {
            "move_type": "in_invoice",
            "partner_id": self.producer_id.commercial_partner_id.id,
            "invoice_date": self.date,
            "date": self.date,
            "journal_id": self.journal_id.id,
            "ref": self.coe or False,
            "narration": self._build_narration(),
            "invoice_line_ids": [(0, 0, line_vals)],
        }

        bill = self.env["account.move"].create(bill_vals)
        bill.action_post()

        liquidation.move_id = bill.id
        liquidation.state = "posted"

        return {
            "type": "ir.actions.act_window",
            "name": _("Liquidación (LPG)"),
            "res_model": "grain.liquidation",
            "res_id": liquidation.id,
            "view_mode": "form",
            "target": "current",
        }

    def _build_narration(self):
        parts = []
        if self.coe:
            parts.append(f"COE: {self.coe}")
        if self.delivery_date:
            parts.append(f"Fecha entrega: {self.delivery_date}")
        if self.port:
            parts.append(f"Puerto: {self.port}")
        if self.grain_grade:
            parts.append(f"Grado: {self.grain_grade}")
        if self.broker_id:
            parts.append(f"Corredor: {self.broker_id.display_name}")
        return " | ".join(parts) if parts else False
