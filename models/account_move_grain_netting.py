# -*- coding: utf-8 -*-
from odoo import models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_open_grain_netting_wizard(self):
        self.ensure_one()
        action = self.env.ref("grain_canje_triangular.action_grain_netting_wizard").read()[0]
        action["context"] = {
            "default_move_id": self.id,
            "default_producer_id": self.partner_id.id,
            "default_company_id": self.company_id.id,
            "default_amount": self.amount_residual,
        }
        return action
