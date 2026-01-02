# -*- coding: utf-8 -*-
from odoo import fields, models


class RegisterGrainLSGWizard(models.TransientModel):
    _inherit = "register.grain.lsg.wizard"

    # Alias por compatibilidad con vistas viejas:
    # NO almacenamos en DB (store=False implícito en related sin store)
    grade = fields.Char(string="Grado", related="grain_grade", readonly=False)

    subtotal = fields.Monetary(string="Subtotal", related="amount_untaxed", readonly=True, currency_field="currency_id")
    tax_amount = fields.Monetary(string="IVA", related="amount_tax", readonly=True, currency_field="currency_id")
    total = fields.Monetary(string="Total", related="amount_total", readonly=True, currency_field="currency_id")
