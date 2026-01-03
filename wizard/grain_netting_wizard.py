# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GrainNettingWizard(models.TransientModel):
    _name = "grain.netting.wizard"
    _description = "Compensación Canje (A/R vs A/P)"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    move_id = fields.Many2one(
        "account.move",
        string="Factura cliente (Insumos)",
        required=True,
        readonly=True,
    )

    producer_id = fields.Many2one(
        "res.partner",
        string="Productor",
        required=True,
        readonly=True,
    )

    # Moneda de la factura (documento)
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        readonly=True,
    )

    lpg_bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill LPG",
        domain="[('move_type','=','in_invoice'),('state','=','posted'),('payment_state','!=','paid'),('partner_id','=',producer_id)]",
        required=True,
    )

    amount = fields.Monetary(
        string="Importe a compensar",
        currency_field="currency_id",
        required=True,
    )

    # -------------------------
    # Helpers multi-moneda
    # -------------------------
    def _move_residual_in_currency(self, move, currency):
        """Residual del move en 'currency' usando amount_residual_currency de las líneas AR/AP si existe."""
        self.ensure_one()
        rp_lines = move.line_ids.filtered(
            lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
        )
        if rp_lines and "amount_residual_currency" in rp_lines._fields:
            # Si el move tiene currency distinta a company, esas líneas suelen tener currency_id = move.currency_id
            if currency and rp_lines[:1].currency_id == currency:
                return sum(rp_lines.mapped("amount_residual_currency"))
        # Fallback: en moneda compañía o si no hay residual_currency confiable
        if currency == move.company_id.currency_id:
            return move.amount_residual
        # Convertimos residual compañía -> currency
        date = move.invoice_date or move.date or fields.Date.context_today(self)
        return move.company_id.currency_id._convert(move.amount_residual, currency, move.company_id, date)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        move_id = self.env.context.get("active_id")
        if not move_id:
            return res

        inv = self.env["account.move"].browse(move_id).exists()
        if not inv:
            return res

        res["move_id"] = inv.id
        res["company_id"] = inv.company_id.id
        res["producer_id"] = inv.partner_id.id

        # Moneda del invoice
        res["currency_id"] = inv.currency_id.id

        # Amount default: residual en moneda del invoice
        amount = self._move_residual_in_currency(inv, inv.currency_id)
        # Si ya está pagada: 0
        res["amount"] = max(amount, 0.0)

        return res

    def action_net(self):
        self.ensure_one()

        if self.move_id.move_type != "out_invoice" or self.move_id.state != "posted":
            raise UserError(_("La factura cliente debe estar publicada (posted)."))

        if self.lpg_bill_id.move_type != "in_invoice" or self.lpg_bill_id.state != "posted":
            raise UserError(_("La vendor bill LPG debe estar publicada (posted)."))

        if not self.company_id.grain_netting_journal_id:
            raise UserError(_("Configurá el diario de compensaciones (Ajustes)."))

        if self.amount <= 0:
            raise UserError(_("El importe debe ser mayor a 0."))

        company = self.company_id
        company_cur = company.currency_id
        inv_cur = self.move_id.currency_id
        bill_cur = self.lpg_bill_id.currency_id
        date = self.move_id.invoice_date or self.move_id.date or fields.Date.context_today(self)

        # Residuales comparados en moneda de la factura (inv_cur)
        inv_res = self._move_residual_in_currency(self.move_id, inv_cur)

        # Bill residual convertido a inv_cur si hace falta
        bill_res_billcur = self._move_residual_in_currency(self.lpg_bill_id, bill_cur)
        if bill_cur != inv_cur:
            bill_res = bill_cur._convert(bill_res_billcur, inv_cur, company, date)
        else:
            bill_res = bill_res_billcur

        max_net = min(inv_res, bill_res)
        if self.amount - max_net > 0.00001:
            raise UserError(_("El importe excede el residual (máx: %s).") % max_net)

        partner = self.producer_id
        recv_acc = partner.property_account_receivable_id
        pay_acc = partner.property_account_payable_id
        if not recv_acc or not pay_acc:
            raise UserError(_("El productor debe tener cuentas por cobrar y por pagar configuradas."))

        # Convertimos el amount (en moneda de invoice) a moneda compañía para el asiento
        amount_company = inv_cur._convert(self.amount, company_cur, company, date)

        journal = company.grain_netting_journal_id

        # Construimos líneas:
        # - Dr A/P (pagar) por amount_company (y amount_currency si bill está en otra moneda)
        # - Cr A/R (cobrar) por amount_company (y amount_currency si invoice está en otra moneda)
        line_pay_vals = {
            "name": _("Compensación Canje (Dr A/P)"),
            "partner_id": partner.id,
            "account_id": pay_acc.id,
            "debit": amount_company,
            "credit": 0.0,
        }
        if bill_cur != company_cur:
            # amount_currency en moneda bill
            amt_bill = inv_cur._convert(self.amount, bill_cur, company, date) if inv_cur != bill_cur else self.amount
            line_pay_vals.update({
                "currency_id": bill_cur.id,
                "amount_currency": amt_bill,
            })

        line_recv_vals = {
            "name": _("Compensación Canje (Cr A/R)"),
            "partner_id": partner.id,
            "account_id": recv_acc.id,
            "debit": 0.0,
            "credit": amount_company,
        }
        if inv_cur != company_cur:
            line_recv_vals.update({
                "currency_id": inv_cur.id,
                "amount_currency": -self.amount,
            })

        net_move = self.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "ref": f"Compensación Canje: {self.move_id.name} vs {self.lpg_bill_id.name}",
            "journal_id": journal.id,
            "company_id": company.id,
            "line_ids": [
                (0, 0, line_pay_vals),
                (0, 0, line_recv_vals),
            ],
        })
        net_move.action_post()

        # Reconciliar A/R contra la factura cliente
        recv_line_net = net_move.line_ids.filtered(lambda l: l.account_id == recv_acc and l.credit > 0 and not l.reconciled)
        recv_lines_inv = self.move_id.line_ids.filtered(lambda l: l.account_id == recv_acc and not l.reconciled)
        (recv_line_net + recv_lines_inv).reconcile()

        # Reconciliar A/P contra la vendor bill LPG
        pay_line_net = net_move.line_ids.filtered(lambda l: l.account_id == pay_acc and l.debit > 0 and not l.reconciled)
        pay_lines_bill = self.lpg_bill_id.line_ids.filtered(lambda l: l.account_id == pay_acc and not l.reconciled)
        (pay_line_net + pay_lines_bill).reconcile()

        return {
            "type": "ir.actions.act_window",
            "name": _("Asiento de compensación"),
            "res_model": "account.move",
            "res_id": net_move.id,
            "view_mode": "form",
        }
