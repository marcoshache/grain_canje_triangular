# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GrainLiquidation(models.Model):
    _inherit = 'grain.liquidation'

    # Si ya existe en el modelo base, esta redefinición es compatible (mismo tipo)
    vendor_bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill (LPG)',
        readonly=True,
        copy=False,
    )

    def _find_vendor_bill_candidate(self):
        """Heurística: busca la vendor bill generada por esta LPG."""
        self.ensure_one()

        producer = getattr(self, 'producer_id', False) or getattr(self, 'partner_id', False)
        date = getattr(self, 'date', False) or getattr(self, 'invoice_date', False)
        journal = getattr(self, 'liquidation_journal_id', False) or getattr(self, 'journal_id', False)

        domain = [('move_type', '=', 'in_invoice'), ('state', 'in', ['draft', 'posted'])]

        if producer:
            domain.append(('partner_id', '=', producer.commercial_partner_id.id))
        if date:
            domain.append(('invoice_date', '=', date))
        if journal:
            domain.append(('journal_id', '=', journal.id))

        key = getattr(self, 'name', False) or self.display_name
        move = self.env['account.move'].search(domain + [('ref', 'ilike', key)], order='id desc', limit=1)
        if not move:
            # fallback: por partner+fecha+diario
            move = self.env['account.move'].search(domain, order='id desc', limit=1)
        return move

    def action_publish(self):
        res = super().action_publish()
        for rec in self:
            if not getattr(rec, 'vendor_bill_id', False):
                move = rec._find_vendor_bill_candidate()
                if move:
                    rec.vendor_bill_id = move.id
        return res

    def action_sync_vendor_bill(self):
        """Botón/acción manual: vincula la vendor bill si quedó vacía."""
        for rec in self:
            move = rec._find_vendor_bill_candidate()
            if not move:
                raise UserError(_("No pude encontrar una Vendor Bill candidata para esta LPG."))
            rec.vendor_bill_id = move.id
        return True
