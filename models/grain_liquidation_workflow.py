# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GrainLiquidation(models.Model):
    _inherit = "grain.liquidation"

    def _get_bridge_account(self):
        self.ensure_one()
        account = self.company_id.grain_clearing_account_id
        if not account:
            raise UserError(_("Falta configurar la Cuenta puente (Granos a liquidar / Canje) en Ajustes."))
        return account

    def _get_liquidation_journal(self):
        self.ensure_one()
        journal = self.company_id.grain_liquidation_journal_id
        if not journal:
            raise UserError(_("Falta configurar el Diario de Liquidaciones de Granos en Ajustes."))
        return journal

    def _ensure_vendor_bill(self):
        """Crea la Vendor Bill si no existe (o reutiliza la existente)."""
        self.ensure_one()

        # Si ya existe, no recreamos
        if getattr(self, "vendor_bill_id", False):
            return self.vendor_bill_id

        # Campos esperados en el modelo base
        producer = getattr(self, "producer_id", False)
        product = getattr(self, "product_id", False)
        amount = getattr(self, "amount", 0.0)
        date = getattr(self, "date", fields.Date.context_today(self))
        toneladas = getattr(self, "toneladas", 0.0)
        price_tn = getattr(self, "price_tn", 0.0) or getattr(self, "precio_tn", 0.0)

        if not producer:
            raise UserError(_("Debe indicar el Productor."))
        if not product:
            raise UserError(_("Debe indicar el Producto servicio (Grano - Liquidación)."))
        if not amount:
            # Si no hay amount calculado, lo intentamos calcular
            if toneladas and price_tn:
                amount = toneladas * price_tn
            if not amount:
                raise UserError(_("El Importe es 0. Verifique Toneladas y Precio por TN."))

        journal = self._get_liquidation_journal()
        bridge_account = self._get_bridge_account()

        qty = toneladas if toneladas else 1.0
        price_unit = price_tn if toneladas and price_tn else amount

        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": producer.id,
            "invoice_date": date,
            "date": date,
            "journal_id": journal.id,
            "invoice_line_ids": [(0, 0, {
                "product_id": product.id,
                "name": getattr(product, "display_name", "LPG"),
                "quantity": qty,
                "price_unit": price_unit,
                # Clave: imputar a la cuenta puente para que el asiento impacte "Granos a liquidar / Canje"
                "account_id": bridge_account.id,
            })],
        })

        # Guardamos relación si el campo existe
        if "vendor_bill_id" in self._fields:
            self.vendor_bill_id = bill.id

        return bill

    def action_post(self):
        """Publicar / Confirmar LPG"""
        for rec in self:
            # Si el modelo original ya trae action_post, lo respetamos
            try:
                return super(GrainLiquidation, rec).action_post()
            except Exception:
                pass

            bill = rec._ensure_vendor_bill()
            if bill.state != "posted":
                bill.action_post()

            if "state" in rec._fields:
                # Estado típico: draft/posted/cancel
                rec.state = "posted"
        return True

    def action_publish(self):
        """Alias por si la vista llama 'publish' en lugar de post."""
        return self.action_post()

    def action_cancel(self):
        for rec in self:
            # Si el modelo original ya trae action_cancel, lo respetamos
            try:
                return super(GrainLiquidation, rec).action_cancel()
            except Exception:
                pass

            bill = getattr(rec, "vendor_bill_id", False)
            if bill and bill.state == "posted":
                raise UserError(_("La Vendor Bill está publicada. Primero cancele/revierta la factura para cancelar la LPG."))

            if "state" in rec._fields:
                rec.state = "cancel"
        return True

    def action_set_draft(self):
        for rec in self:
            bill = getattr(rec, "vendor_bill_id", False)
            if bill and bill.state == "posted":
                raise UserError(_("No puede volver a borrador si la Vendor Bill está publicada."))
            if "state" in rec._fields:
                rec.state = "draft"
        return True
