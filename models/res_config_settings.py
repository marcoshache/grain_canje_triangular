# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Config actual del módulo
    canje_account_id = fields.Many2one(
        "account.account",
        string="Cuenta Cta Cte Cereal Productor",
        related="company_id.canje_account_id",
        readonly=False,
    )
    canje_journal_id = fields.Many2one(
        "account.journal",
        string="Diario de Canje",
        related="company_id.canje_journal_id",
        readonly=False,
    )

    # NUEVO: LPG/LSG + netting (Tramo A)
    grain_clearing_account_id = fields.Many2one(
        "account.account",
        string="Cuenta puente Granos a liquidar / Canje",
        related="company_id.grain_clearing_account_id",
        readonly=False,
    )
    grain_liquidation_journal_id = fields.Many2one(
        "account.journal",
        string="Diario Liquidaciones de Granos",
        related="company_id.grain_liquidation_journal_id",
        readonly=False,
    )
    grain_netting_journal_id = fields.Many2one(
        "account.journal",
        string="Diario Compensaciones Canje",
        related="company_id.grain_netting_journal_id",
        readonly=False,
    )
