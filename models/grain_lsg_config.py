# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    grain_lsg_tax_id = fields.Many2one(
        "account.tax",
        string="IVA compra default LSG",
        help="Impuesto por defecto para Liquidación Secundaria de Granos (LSG).",
        domain=[("type_tax_use", "=", "purchase")],
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    grain_lsg_tax_id = fields.Many2one(
        "account.tax",
        string="IVA compra default LSG",
        related="company_id.grain_lsg_tax_id",
        readonly=False,
        domain=[("type_tax_use", "=", "purchase")],
    )
