# -*- coding: utf-8 -*-
from odoo import fields, models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    canje_application_ids = fields.One2many(
        "grain.canje.application",
        "move_id",
        string="Aplicaciones de canje",
        readonly=True,
    )

    def button_apply_grain_canje(self):
        """Abrir wizard de aplicación de canje de granos para esta factura de proveedor."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aplicar canje de granos"),
            "res_model": "apply.grain.canje.wizard",
            "view_mode": "form",
            "view_id": self.env.ref(
                "grain_canje_triangular.view_apply_grain_canje_wizard"
            ).id,
            "target": "new",
            "context": {
                "default_move_id": self.id,
            },
        }
