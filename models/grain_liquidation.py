# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GrainLiquidation(models.Model):
    _name = "grain.liquidation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Liquidación de Granos (LPG/LSG)"
    _order = "date desc, id desc"

    name = fields.Char(string="Número", readonly=True, copy=False, default=lambda self: _("New"))
    date = fields.Date(required=True, default=fields.Date.context_today)

    liquidation_type = fields.Selection(
        [("lpg", "LPG"), ("lsg", "LSG")],
        string="Tipo",
        required=True,
        default="lpg",
        tracking=True,
    )

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)

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

    qty_tn = fields.Float(string="Toneladas", required=True)
    price_per_tn = fields.Monetary(string="Precio por TN", required=True, currency_field="currency_id")

    tax_id = fields.Many2one(
        "account.tax",
        string="IVA (compra)",
        domain="[('type_tax_use','=','purchase')]",
    )

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

    move_id = fields.Many2one("account.move", string="Comprobante (LPG/LSG)", readonly=True, copy=False)
    payment_id = fields.Many2one("account.payment", string="Pago (LSG)", readonly=True, copy=False)

    state = fields.Selection(
        [("draft", "Borrador"), ("posted", "Publicado"), ("cancel", "Cancelado")],
        default="draft",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            name = vals.get("name")
            if not name or name in ("/", "New", _("New")):
                ltype = vals.get("liquidation_type") or self.env.context.get("default_liquidation_type") or "lpg"
                code = "grain.liquidation.lsg" if ltype == "lsg" else "grain.liquidation.lpg"
                vals["name"] = self.env["ir.sequence"].next_by_code(code) or _("New")
        return super().create(vals_list)



    @api.onchange("liquidation_type", "company_id")
    def _onchange_liquidation_type_tax(self):
        for rec in self:
            if not rec.company_id:
                continue
            if rec.liquidation_type == "lsg":
                rec.tax_id = rec.company_id.grain_lsg_tax_id
            else:
                rec.tax_id = rec.company_id.grain_lpg_tax_id

    @api.depends("qty_tn", "price_per_tn", "tax_id", "currency_id")
    def _compute_amounts(self):
        for rec in self:
            base = (rec.qty_tn or 0.0) * (rec.price_per_tn or 0.0)
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

    def action_open_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No hay comprobante vinculado."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Comprobante"),
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "views": [(self.env.ref("account.view_move_form").id, "form")],
            "target": "current",
        }

    def action_open_bill(self):
        return self.action_open_move()
