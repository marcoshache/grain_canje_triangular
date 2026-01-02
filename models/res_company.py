# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    canje_account_id = fields.Many2one("account.account", string="Cuenta Canje")
    canje_journal_id = fields.Many2one("account.journal", string="Diario Canje")

    grain_clearing_account_id = fields.Many2one("account.account", string="Cuenta puente Granos / Canje")
    grain_liquidation_journal_id = fields.Many2one("account.journal", string="Diario Liquidaciones de Granos")

    grain_netting_journal_id = fields.Many2one("account.journal", string="Diario Compensaciones (Asiento)")

    # NUEVO: diario para pagos (bank/cash) para que el motor de retenciones pueda actuar
    grain_netting_payment_journal_id = fields.Many2one(
        "account.journal",
        string="Diario Compensaciones (Pago)",
        domain="[('type','in',('bank','cash')), ('company_id','=',id)]",
        help="Se usa cuando la compensación se registra como pagos (inbound/outbound). "
             "Recomendado para disparar retenciones si están configuradas.",
    )

    grain_lpg_tax_id = fields.Many2one("account.tax", string="IVA compra default LPG")
