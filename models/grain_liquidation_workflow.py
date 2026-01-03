# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class GrainLiquidation(models.Model):
    _inherit = "grain.liquidation"

    def _get_bridge_account(self):
        self.ensure_one()
        account = self.clearing_account_id or self.company_id.grain_clearing_account_id
        if not account:
            raise UserError(_("Falta configurar la Cuenta puente (Granos a liquidar / Canje) en Ajustes."))
        return account

    def _get_liquidation_journal(self):
        self.ensure_one()
        journal = self.journal_id or self.company_id.grain_liquidation_journal_id
        if not journal:
            raise UserError(_("Falta configurar el Diario de Liquidaciones de Granos en Ajustes."))
        return journal

    def _get_lsg_payment_journal(self):
        self.ensure_one()
        journal = self.company_id.grain_netting_payment_journal_id
        if not journal:
            raise UserError(_("Falta configurar el Diario Compensaciones (Pago/Cobro) en Ajustes."))
        return journal

    def _ensure_move_lpg(self):
        """Crea la Vendor Bill solo para LPG."""
        self.ensure_one()
        if self.move_id:
            return self.move_id

        if self.liquidation_type != "lpg":
            return False

        producer = self.producer_id
        product = self.product_id
        date = self.date or fields.Date.context_today(self)

        qty = self.qty_tn or 0.0
        price_unit = self.price_per_tn or 0.0
        amount = (qty * price_unit)

        if not producer:
            raise UserError(_("Debe indicar el Productor."))
        if not product:
            raise UserError(_("Debe indicar el Producto servicio (Grano - Liquidación)."))
        if not amount:
            raise UserError(_("El Importe es 0. Verifique Toneladas y Precio por TN."))

        journal = self._get_liquidation_journal()
        bridge_account = self._get_bridge_account()

        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": producer.commercial_partner_id.id,
            "invoice_date": date,
            "date": date,
            "journal_id": journal.id,
            "ref": f"LPG {self.name}",
            "invoice_line_ids": [(0, 0, {
                "product_id": product.id,
                "name": product.display_name or "LPG",
                "quantity": qty or 1.0,
                "price_unit": price_unit or amount,
                "account_id": bridge_account.id,
                "tax_ids": [(6, 0, [self.tax_id.id])] if self.tax_id else False,
            })],
        })

        self.move_id = bill.id
        return bill

    def _ensure_payment_lsg(self):
        """Crea el pago (en especie) solo para LSG."""
        self.ensure_one()
        if self.payment_id:
            return self.payment_id

        if self.liquidation_type != "lsg":
            return False

        # A quién se le paga: si hay corredor, paga al corredor; si no, al productor
        partner = (self.broker_id or self.producer_id)
        if not partner:
            raise UserError(_("Debe indicar Corredor o Productor para el pago LSG."))

        if not self.amount_total:
            raise UserError(_("El Total es 0. Verifique Toneladas, Precio y IVA."))

        journal = self._get_lsg_payment_journal()

        method_line = journal.outbound_payment_method_line_ids.filtered(lambda l: l.code == "manual")[:1] \
                      or journal.outbound_payment_method_line_ids[:1]
        if not method_line:
            raise UserError(_("El diario %s no tiene método de pago de salida configurado.") % (journal.display_name,))

        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": partner.commercial_partner_id.id,
            "amount": self.amount_total,
            "currency_id": self.currency_id.id,
            "date": self.date or fields.Date.context_today(self),
            "journal_id": journal.id,
            "payment_method_line_id": method_line.id,
            "ref": f"LSG {self.name}",
        })
        payment.action_post()

        self.payment_id = payment.id
        return payment

    def action_post(self):
        for rec in self:
            # LPG => bill / LSG => payment
            if rec.liquidation_type == "lpg":
                bill = rec._ensure_move_lpg()
                if bill and bill.state != "posted":
                    bill.action_post()
            else:
                rec._ensure_payment_lsg()

            rec.state = "posted"
        return True

    def action_publish(self):
        return self.action_post()

    def action_cancel(self):
        for rec in self:
            if rec.liquidation_type == "lpg":
                bill = rec.move_id
                if bill and bill.state == "posted":
                    raise UserError(_("El comprobante está publicado. Primero cancele/revierta la factura."))
            else:
                pay = rec.payment_id
                if pay and pay.state == "posted":
                    raise UserError(_("El pago está publicado. Primero cancele/revierta el pago."))

            rec.state = "cancel"
        return True

    def action_set_draft(self):
        for rec in self:
            if rec.liquidation_type == "lpg" and rec.move_id and rec.move_id.state == "posted":
                raise UserError(_("No puede volver a borrador si el comprobante está publicado."))
            if rec.liquidation_type == "lsg" and rec.payment_id and rec.payment_id.state == "posted":
                raise UserError(_("No puede volver a borrador si el pago está publicado."))
            rec.state = "draft"
        return True
