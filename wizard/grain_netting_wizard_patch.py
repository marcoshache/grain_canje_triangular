# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GrainNettingWizard(models.TransientModel):
    _inherit = "grain.netting.wizard"

    # -------------------------------------------------------------------------
    # Helpers (NO ensure_one aquí: default_get/onchange llaman con recordset vacío)
    # -------------------------------------------------------------------------
    @api.model
    def _rp_lines(self, move):
        """Receivable/Payable lines del move."""
        return move.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )

    @api.model
    def _move_residual_in_currency(self, move, currency):
        """
        Residual POSITIVO en 'currency' (abs).
        Funciona aunque Odoo tenga signos negativos en payable.
        """
        if not move:
            return 0.0

        lines = self._rp_lines(move)
        if not lines:
            return 0.0

        company = move.company_id
        date = move.invoice_date or move.date or fields.Date.context_today(self)

        # 1) Si existe amount_residual_currency en líneas y la moneda coincide
        if "amount_residual_currency" in lines._fields:
            # Si la línea tiene moneda igual a la que pedimos, usamos residual_currency
            # Ojo: a veces line.currency_id puede ser False y ahí aplica company currency
            if currency and lines[:1].currency_id and lines[:1].currency_id.id == currency.id:
                return abs(sum(lines.mapped("amount_residual_currency")))

        # 2) Fallback: residual en moneda compañía (amount_residual) y convertimos
        residual_company = abs(sum(lines.mapped("amount_residual")))
        if not currency or currency.id == company.currency_id.id:
            return residual_company

        return currency._convert(
            residual_company,
            currency,
            company,
            date,
            round=False,
        )

    @api.model
    def _netting_max_amount(self, inv, lpg_bill, currency):
        """Máximo compensable (positivo) en moneda currency."""
        if not inv or not lpg_bill:
            return 0.0
        r_inv = self._move_residual_in_currency(inv, currency)
        r_lpg = self._move_residual_in_currency(lpg_bill, currency)
        return max(0.0, min(r_inv, r_lpg))

    # -------------------------------------------------------------------------
    # Defaults / UI behavior
    # -------------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)

        inv_id = self.env.context.get("active_id")
        if inv_id:
            inv = self.env["account.move"].browse(inv_id).exists()
            if inv:
                vals.setdefault("move_id", inv.id)
                vals.setdefault("producer_id", inv.partner_id.id)
                vals.setdefault("company_id", inv.company_id.id)
                # moneda del documento (USD si la factura está en USD)
                vals.setdefault("currency_id", inv.currency_id.id)

                # default amount = residual de la factura en su moneda
                currency = inv.currency_id
                vals["amount"] = self._move_residual_in_currency(inv, currency)

        return vals

    @api.onchange("move_id", "lpg_bill_id", "currency_id", "amount")
    def _onchange_amount_cap(self):
        """Si el usuario pone más que el máximo, capeamos en vez de error."""
        for w in self:
            if not w.move_id or not w.lpg_bill_id:
                continue
            currency = w.currency_id or w.move_id.currency_id
            max_amt = w._netting_max_amount(w.move_id, w.lpg_bill_id, currency)
            if max_amt > 0 and w.amount and w.amount > max_amt:
                w.amount = max_amt

    # -------------------------------------------------------------------------
    # Action
    # -------------------------------------------------------------------------
    def action_compensate(self):
        """
        Evita el error del residual negativo y permite que si te pasás,
        compense al máximo posible.
        """
        self.ensure_one()

        if not self.move_id or not self.lpg_bill_id:
            raise UserError(_("Seleccioná la factura cliente y la LPG."))

        currency = self.currency_id or self.move_id.currency_id
        max_amt = self._netting_max_amount(self.move_id, self.lpg_bill_id, currency)

        if max_amt <= 0:
            raise UserError(_("No hay saldo para compensar entre la factura y la LPG."))

        if not self.amount or self.amount <= 0:
            raise UserError(_("El importe a compensar debe ser mayor a 0."))

        # Si se excede, capeamos (NO error)
        if self.amount > max_amt:
            self.amount = max_amt

        return super().action_compensate()
