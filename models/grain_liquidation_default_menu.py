# -*- coding: utf-8 -*-
from odoo import api, models


class GrainLiquidation(models.Model):
    _inherit = "grain.liquidation"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context or {}

        # Si llega explícito, gana
        dtype = ctx.get("default_liquidation_type")
        if dtype in ("lpg", "lsg"):
            res["liquidation_type"] = dtype
            return res

        # Fallback: inferir por la acción desde la que se abrió (listado LSG/LPG)
        params = ctx.get("params") or {}
        action_id = params.get("action") or ctx.get("action")

        try:
            action_id = int(action_id) if action_id else 0
        except Exception:
            action_id = 0

        if not action_id:
            return res

        act_lsg = 0
        act_lpg = 0
        try:
            act_lsg = self.env.ref("grain_canje_triangular.action_grain_liquidation_lsg").id
        except Exception:
            pass
        try:
            act_lpg = self.env.ref("grain_canje_triangular.action_grain_liquidation_lpg").id
        except Exception:
            pass

        if act_lsg and action_id == act_lsg:
            res["liquidation_type"] = "lsg"
        elif act_lpg and action_id == act_lpg:
            res["liquidation_type"] = "lpg"

        return res
