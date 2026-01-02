# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    canje_account_id = fields.Many2one(related="company_id.canje_account_id", readonly=False)
    canje_journal_id = fields.Many2one(related="company_id.canje_journal_id", readonly=False)

    grain_clearing_account_id = fields.Many2one(related="company_id.grain_clearing_account_id", readonly=False)
    grain_liquidation_journal_id = fields.Many2one(related="company_id.grain_liquidation_journal_id", readonly=False)

    grain_netting_journal_id = fields.Many2one(related="company_id.grain_netting_journal_id", readonly=False)

    # NUEVO
    grain_netting_payment_journal_id = fields.Many2one(
        related="company_id.grain_netting_payment_journal_id",
        readonly=False
    )

    grain_lpg_tax_id = fields.Many2one(related="company_id.grain_lpg_tax_id", readonly=False)
