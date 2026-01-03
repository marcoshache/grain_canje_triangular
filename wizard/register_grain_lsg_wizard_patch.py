# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RegisterGrainLSGWizard(models.TransientModel):
    _inherit = "register.grain.lsg.wizard"

    # Alias para compatibilidad si alguna vista/acción usa "grade"
    grade = fields.Char(string="Grado", related="grain_grade", readonly=False)

    # Alias NO almacenados (evita columnas faltantes en la tabla transient)
    subtotal = fields.Monetary(string="Subtotal", currency_field="currency_id",
                               compute="_compute_alias_amounts", store=False)
    tax_amount = fields.Monetary(string="IVA", currency_field="currency_id",
                                 compute="_compute_alias_amounts", store=False)
    total = fields.Monetary(string="Total", currency_field="currency_id",
                            compute="_compute_alias_amounts", store=False)

    net_amount = fields.Monetary(string="Neto", currency_field="currency_id",
                                 compute="_compute_alias_amounts", store=False)
    gross_amount = fields.Monetary(string="Bruto", currency_field="currency_id",
                                   compute="_compute_alias_amounts", store=False)

    @api.depends("amount_untaxed", "amount_tax", "amount_total")
    def _compute_alias_amounts(self):
        for rec in self:
            rec.subtotal = rec.amount_untaxed
            rec.tax_amount = rec.amount_tax
            rec.total = rec.amount_total
            rec.net_amount = rec.amount_untaxed
            rec.gross_amount = rec.amount_total
