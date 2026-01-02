# -*- coding: utf-8 -*-
from odoo import models


class GrainLiquidation(models.Model):
    _inherit = "grain.liquidation"

    # Compat: si alguna vista/acción vieja llama a "vendor bill"
    def action_open_vendor_bill(self):
        return self.action_open_move()
