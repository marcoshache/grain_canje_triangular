# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GrainLiquidation(models.Model):
    _inherit = "grain.liquidation"

    liquidation_type = fields.Selection(
        [
            ("lpg", "LPG (Primaria)"),
            ("lsg", "LSG (Secundaria)"),
        ],
        string="Tipo",
        default="lpg",
        required=True,
        tracking=True,
        index=True,
    )

    # Para LSG: factura del proveedor a la que se le aplicará el pago
    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Factura proveedor a pagar",
        domain="[('move_type','=','in_invoice'),('state','=','posted'),('payment_state','!=','paid')]",
        copy=False,
    )

    def name_get(self):
        res = []
        for rec in self:
            prefix = "LPG" if rec.liquidation_type == "lpg" else "LSG"
            number = rec.name or str(rec.id)
            res.append((rec.id, f"{prefix} {number}"))
        return res

    def action_open_payment(self):
        self.ensure_one()
        if not getattr(self, "payment_id", False):
            raise UserError(_("No hay pago vinculado."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Pago"),
            "res_model": "account.payment",
            "res_id": self.payment_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _ensure_lsg_payment(self):
        self.ensure_one()

        if not getattr(self, "payment_id", False):
            pass
        else:
            return self.payment_id

        journal = self.company_id.grain_netting_payment_journal_id
        if not journal:
            raise UserError(_("Configurá el Diario Compensaciones (Pago) en la compañía."))

        bill = self.vendor_bill_id
        if not bill:
            raise UserError(_("Seleccioná la Factura proveedor a pagar (LSG)."))

        if bill.move_type != "in_invoice" or bill.state != "posted":
            raise UserError(_("La factura del proveedor debe estar Publicada (posted)."))

        if bill.payment_state == "paid":
            raise UserError(_("La factura del proveedor ya está Pagada."))

        amount = self.amount_total or 0.0
        if amount <= 0:
            raise UserError(_("El Total de la LSG es 0. Verificá Toneladas/Precio e IVA."))

        ctx = dict(self.env.context or {})
        ctx.update(active_model="account.move", active_ids=bill.ids)

        communication = f"LSG {self.name or self.id}"
        if self.coe:
            communication = f"{communication} / COE {self.coe}"

        register = self.env["account.payment.register"].with_context(ctx).create({
            "payment_date": self.date or fields.Date.context_today(self),
            "journal_id": journal.id,
            "amount": amount,
            "communication": communication,
        })

        payments = register._create_payments()
        payment = payments[:1]
        if not payment:
            raise UserError(_("No se pudo generar el pago."))

        # Linkeo
        self.payment_id = payment.id
        # Usamos move_id como “comprobante” (asiento del pago)
        self.move_id = payment.move_id.id
        return payment

    def action_post(self):
        """Si es LSG: genera pago y concilia contra la factura del proveedor."""
        for rec in self:
            if rec.liquidation_type == "lsg":
                rec._ensure_lsg_payment()
                rec.state = "posted"
            else:
                # LPG: mantiene el flujo existente (vendor bill por puente)
                super(GrainLiquidation, rec).action_post()
        return True
