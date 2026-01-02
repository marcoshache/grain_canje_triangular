# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RegisterGrainLpgWizard(models.TransientModel):
    _name = "register.grain.lpg.wizard"
    _description = "Registrar LPG (vendor bill al productor)"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    date = fields.Date(required=True, default=fields.Date.context_today)
    producer_id = fields.Many2one("res.partner", string="Productor", required=True, domain="[('supplier_rank','>',0)]")

    product_id = fields.Many2one(
        "product.product",
        string="Producto servicio (Grano - Liquidación)",
        required=True,
        domain="[('detailed_type','=','service')]",
    )

    qty_tn = fields.Float(string="Toneladas", required=True)
    price_per_tn = fields.Monetary(string="Precio por TN", required=True, currency_field="currency_id")
    amount = fields.Monetary(string="Importe", compute="_compute_amount", currency_field="currency_id", store=False)

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

    @api.depends("qty_tn", "price_per_tn")
    def _compute_amount(self):
        for w in self:
            w.amount = (w.qty_tn or 0.0) * (w.price_per_tn or 0.0)

    def action_create_lpg(self):
        self.ensure_one()

        if not self.company_id.grain_clearing_account_id:
            raise UserError(_("Configurá la cuenta puente en Ajustes (Granos a liquidar / Canje)."))
        if not self.company_id.grain_liquidation_journal_id:
            raise UserError(_("Configurá el diario de liquidaciones de granos en Ajustes."))

        if self.qty_tn <= 0:
            raise UserError(_("Las toneladas deben ser mayores a 0."))

        lpg = self.env["grain.liquidation"].create({
            "date": self.date,
            "company_id": self.company_id.id,
            "producer_id": self.producer_id.id,
            "product_id": self.product_id.id,
            "qty_tn": self.qty_tn,
            "price_per_tn": self.price_per_tn,
            "clearing_account_id": self.clearing_account_id.id,
            "journal_id": self.journal_id.id,
        })

        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.producer_id.id,
            "invoice_date": self.date,
            "company_id": self.company_id.id,
            "journal_id": self.journal_id.id,
            "ref": f"LPG {lpg.id}",
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product_id.id,
                "name": _("Liquidación primaria de granos (LPG)"),
                "quantity": self.qty_tn,
                "price_unit": self.price_per_tn,
                "account_id": self.clearing_account_id.id,
            })],
        })
        bill.action_post()

        lpg.write({
            "move_id": bill.id,
            "state": "posted",
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("LPG"),
            "res_model": "grain.liquidation",
            "res_id": lpg.id,
            "view_mode": "form",
        }
