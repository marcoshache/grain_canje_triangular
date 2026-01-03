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

    # Opcional: solo para “referencia” (NO debe ser obligatorio para publicar)
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

    def _get_lsg_partner(self):
        """Partner a quien se le genera el pago (pago a cuenta).
        Preferimos corredor si existe; si no, productor."""
        self.ensure_one()
        return self.broker_id or self.producer_id

    def _ensure_lsg_payment(self):
        """Crea un pago proveedor (prepayment) SIN factura.
        Luego se aplica desde la factura como 'pago/credito pendiente'."""
        self.ensure_one()

        if getattr(self, "payment_id", False):
            return self.payment_id

        journal = self.company_id.grain_netting_payment_journal_id
        if not journal:
            raise UserError(_("Configurá el Diario Compensaciones (Pago) en la compañía."))

        partner = self._get_lsg_partner()
        if not partner:
            raise UserError(_("Seleccioná Corredor o Productor para generar el pago LSG."))

        amount = self.amount_total or 0.0
        if amount <= 0:
            raise UserError(_("El Total de la LSG es 0.\nVerificá Toneladas/Precio e IVA."))

        # Método de pago: outbound (pago a proveedor)
        method_line = journal.outbound_payment_method_line_ids[:1]
        if not method_line:
            raise UserError(_("El diario %s no tiene métodos de pago de salida configurados.") % journal.display_name)

        communication = f"LSG {self.name or self.id}"
        if self.coe:
            communication = f"{communication} / COE {self.coe}"

        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": partner.id,
            "amount": amount,
            "currency_id": self.company_id.currency_id.id,
            "date": self.date or fields.Date.context_today(self),
            "journal_id": journal.id,
            "payment_method_line_id": method_line.id,
            "ref": communication,
        })
        payment.action_post()

        self.payment_id = payment.id
        self.move_id = payment.move_id.id  # “comprobante” asociado
        return payment

    def action_post(self):
        """LSG: genera pago a cuenta (sin factura)."""
        for rec in self:
            if rec.liquidation_type == "lsg":
                rec._ensure_lsg_payment()
                rec.state = "posted"
            else:
                super(GrainLiquidation, rec).action_post()
        return True
