# -*- coding: utf-8 -*-
from odoo import fields, models

class GrainNettingWizard(models.TransientModel):
    _inherit = "grain.netting.wizard"

    # La vista lo referencia; si el modelo lo perdió en algún refactor, lo reponemos.
    liquidation_id = fields.Many2one(
        "grain.liquidation",
        string="Liquidación",
    )
