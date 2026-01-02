# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RegisterGrainLSGWizard(models.TransientModel):
    _name = "register.grain.lsg.wizard"
    _description = "Registrar LSG"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    date = fields.Date(required=True, default=fields.Date.context_today)
    coe = fields.Char(string="C.O.E.")

    producer_id = fields.Many2one(
        "res.partner",
        string="Vendedor (Productor/Proveedor de grano)",
        required=True,
        domain="[('supplier_rank','>',0)]",
    )
    broker_id = fields.Many2one("res.partner", string="Corredor")
    product_id = fields.Many2one(
        "product.product",
        string="Producto servicio (Grano - Liquidación)",
        required=True,
        domain="[('detailed_type','=','service')]",
    )

    delivery_date = fields.Date(string="Fecha entrega")
    port = fields.Char(string="Puerto")
    grain_grade = fields.Char(string="Grado")

    qty_kg = fields.Float(string="Cantidad (Kg)", required=True, default=0.0)
    price_per_kg = fields.Monetary(string="Precio por Kg", required=True, currency_field="currency_id", default=0.0)

    qty_tn = fields.Float(string="Toneladas", compute="_compute_tn_price", store=False)
    price_per_tn = fields.Monetary(string="Precio por TN", compute="_compute_tn_price", store=False, currency_field="currency_id")

    tax_id = fields.Many2one(
        "account.tax",
        string="IVA (compra)",
        domain="[('type_tax_use','=','purchase')]",
        default=lambda self: self.env.company.grain_lsg_tax_id.id,
    )

    amount_untaxed = fields.Monetary(string="Subtotal", compute="_compute_amounts", store=False, currency_field="currency_id")
    amount_tax = fields.Monetary(string="IVA", compute="_compute_amounts", store=False, currency_field="currency_id")
    amount_total = fields.Monetary(string="Total", compute="_compute_amounts", store=False, currency_field="currency_id")

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

    @api.depends("qty_kg", "price_per_kg")
    def _compute_tn_price(self):
        for rec in self:
            rec.qty_tn = (rec.qty_kg or 0.0) / 1000.0
            rec.price_per_tn = (rec.price_per_kg or 0.0) * 1000.0

    @api.depends("qty_kg", "price_per_kg", "tax_id", "currency_id")
    def _compute_amounts(self):
        for rec in self:
            base = (rec.qty_kg or 0.0) * (rec.price_per_kg or 0.0)
            rec.amount_untaxed = base
            rec.amount_tax = 0.0
            rec.amount_total = base
            if rec.tax_id:
                taxes = rec.tax_id.compute_all(
                    base, currency=rec.currency_id, quantity=1.0,
                    product=False, partner=rec.producer_id
                )
                rec.amount_tax = taxes["total_included"] - taxes["total_excluded"]
                rec.amount_total = taxes["total_included"]

    def action_create_lsg(self):
        self.ensure_one()

        if not self.clearing_account_id:
            raise UserError(_("Configurá la Cuenta puente Granos/Canje en la compañía o en el wizard."))
        if not self.journal_id:
            raise UserError(_("Configurá el Diario de Liquidaciones de Granos en la compañía o en el wizard."))

        # Crear liquidación
        liquidation = self.env["grain.liquidation"].create({
            "date": self.date,
            "liquidation_type": "lsg",
            "company_id": self.company_id.id,
            "coe": self.coe,
            "producer_id": self.producer_id.id,
            "broker_id": self.broker_id.id,
            "product_id": self.product_id.id,
            "delivery_date": self.delivery_date,
            "port": self.port,
            "grain_grade": self.grain_grade,
            "qty_tn": self.qty_tn,
            "price_per_tn": self.price_per_tn,
            "tax_id": self.tax_id.id if self.tax_id else False,
            "clearing_account_id": self.clearing_account_id.id,
            "journal_id": self.journal_id.id,
            "state": "draft",
        })

        # Vendor Bill (compra) usando cuenta puente como cuenta del renglón
        bill_vals = {
            "move_type": "in_invoice",
            "partner_id": self.producer_id.id,
            "company_id": self.company_id.id,
            "invoice_date": self.date,
            "date": self.date,
            "journal_id": self.journal_id.id,
            "ref": ("LSG %s%s" % (self.coe + " " if self.coe else "", liquidation.name or "")).strip(),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product_id.id,
                "name": _("LSG - %s") % (self.product_id.display_name,),
                "quantity": self.qty_tn,
                "price_unit": self.price_per_tn,
                "account_id": self.clearing_account_id.id,
                "tax_ids": [(6, 0, [self.tax_id.id])] if self.tax_id else False,
            })],
        }

        bill = self.env["account.move"].create(bill_vals)
        bill.action_post()

        liquidation.write({
            "move_id": bill.id,
            "state": "posted",
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("LSG"),
            "res_model": "grain.liquidation",
            "res_id": liquidation.id,
            "view_mode": "form",
            "target": "current",
        }
