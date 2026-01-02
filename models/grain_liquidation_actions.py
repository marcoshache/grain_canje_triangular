# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError

class GrainLiquidation(models.Model):
    _inherit = 'grain.liquidation'

    def action_open_vendor_bill(self):
        self.ensure_one()
        if not self.vendor_bill_id:
            raise UserError(_("No hay Factura de proveedor (LPG) vinculada."))
        action = self.env.ref('account.action_move_in_invoice_type').read()[0]
        action['res_id'] = self.vendor_bill_id.id
        action['view_mode'] = 'form'
        action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
        return action
