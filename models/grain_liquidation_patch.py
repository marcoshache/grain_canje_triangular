# -*- coding: utf-8 -*-
from odoo import fields, models


class GrainLiquidation(models.Model):
    _inherit = "grain.liquidation"

    # Compatibilidad: algunos XML o código legacy referencian vendor_bill_id.
    # Lo dejamos como related de move_id para evitar duplicaciones y tener una única fuente de verdad.
    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill (LPG)",
        related="move_id",
        store=True,
        readonly=True,
        copy=False,
    )
