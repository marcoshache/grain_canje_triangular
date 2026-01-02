from odoo import models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    # Config actual del módulo (pago a proveedor / canje existente)
    canje_account_id = fields.Many2one(
        "account.account",
        string="Cuenta Cta Cte Cereal Productor",
        help="Cuenta contable para la cuenta corriente de cereal productor.",
    )
    canje_journal_id = fields.Many2one(
        "account.journal",
        string="Diario de Canje",
        help="Diario contable utilizado para las operaciones de canje (pago a proveedor).",
    )

    # NUEVO: Config para LPG/LSG + nettings (Tramo A)
    grain_clearing_account_id = fields.Many2one(
        "account.account",
        string="Cuenta puente Granos a liquidar / Canje",
        help="Cuenta puente conciliable (Activo Corriente) para registrar liquidaciones de granos.",
    )
    grain_liquidation_journal_id = fields.Many2one(
        "account.journal",
        string="Diario Liquidaciones de Granos",
        help="Diario de compras para registrar LPG/LSG (liquidaciones).",
    )
    grain_netting_journal_id = fields.Many2one(
        "account.journal",
        string="Diario Compensaciones Canje",
        help="Diario de asiento (Miscellaneous) para compensaciones/netting (A/R vs A/P, Productor vs Corredor).",
    )
