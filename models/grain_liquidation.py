# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GrainLiquidation(models.Model):
    _name = "grain.liquidation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Liquidación Primaria de Granos (LPG)"
    _order = "date desc, id desc"

    name = fields.Char(string="Número", readonly=True, copy=False, default=lambda self: _("New"))
    date = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)

    producer_id = fields.Many2one(
        "res.partner",
        string="Productor",
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
    amount = fields.Monetary(string="Importe", compute="_compute_amount", store=True, currency_field="currency_id")

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

    move_id = fields.Many2one("account.move", string="Vendor Bill (LPG)", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Borrador"), ("posted", "Publicado"), ("cancel", "Cancelado")],
        default="draft",
        tracking=True,
    )

    @api.depends("qty_tn", "price_per_tn")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.qty_tn or 0.0) * (rec.price_per_tn or 0.0)

    def action_open_bill(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No hay factura (vendor bill) vinculada."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bill (LPG)"),
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }
