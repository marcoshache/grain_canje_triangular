# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RegisterGrainLSGWizard(models.TransientModel):
    _name = "register.grain.lsg.wizard"
    _description = "Registrar LSG (Pago en especie)"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    date = fields.Date(required=True, default=fields.Date.context_today)
    coe = fields.Char(string="C.O.E.")

    # En LSG este partner es el "Proveedor a pagar con la LSG"
    producer_id = fields.Many2one(
        "res.partner",
        string="Proveedor (a pagar con LSG)",
        required=True,
        domain="[('supplier_rank','>',0)]",
    )

    broker_id = fields.Many2one("res.partner", string="Corredor")

    product_id = fields.Many2one(
        "product.product",
        string="Producto servicio (Grano - Liquidación)",
        required=True,
        domain="[('detailed_type','=','service')]",
    )

    delivery_date = fields.Date(string="Fecha entrega")
    port = fields.Char(string="Puerto")
    grain_grade = fields.Char(string="Grado")

    qty_kg = fields.Float(string="Cantidad (Kg)", required=True, default=0.0)
    price_per_kg = fields.Monetary(string="Precio por Kg", required=True, currency_field="currency_id", default=0.0)

    qty_tn = fields.Float(string="Toneladas", compute="_compute_tn_price", store=False)
    price_per_tn = fields.Monetary(string="Precio por TN", compute="_compute_tn_price", store=False, currency_field="currency_id")

    tax_id = fields.Many2one(
        "account.tax",
        string="IVA (compra)",
        domain="[('type_tax_use','=','purchase')]",
        default=lambda self: self.env.company.grain_lsg_tax_id.id,
    )

    amount_untaxed = fields.Monetary(string="Subtotal", compute="_compute_amounts", store=False, currency_field="currency_id")
    amount_tax = fields.Monetary(string="IVA", compute="_compute_amounts", store=False, currency_field="currency_id")
    amount_total = fields.Monetary(string="Total", compute="_compute_amounts", store=False, currency_field="currency_id")

    # En LSG, journal_id ES el diario del pago (no el de compras)
    journal_id = fields.Many2one(
        "account.journal",
        string="Diario de Pago (LSG)",
        default=lambda self: self.env.company.grain_netting_payment_journal_id.id,
        required=True,
    )

    # Se deja por compatibilidad (no lo usamos para el payment; lo usa el asiento del diario)
    clearing_account_id = fields.Many2one(
        "account.account",
        string="Cuenta puente (opcional)",
        default=lambda self: self.env.company.grain_clearing_account_id.id,
        required=False,
    )

    # Aliases para evitar “Missing field string information” si queda alguna vista vieja en cache
    grade = fields.Char(string="Grado (alias)", compute="_compute_alias", store=False)
    subtotal = fields.Monetary(string="Subtotal (alias)", compute="_compute_alias", store=False, currency_field="currency_id")
    tax_amount = fields.Monetary(string="IVA (alias)", compute="_compute_alias", store=False, currency_field="currency_id")
    total = fields.Monetary(string="Total (alias)", compute="_compute_alias", store=False, currency_field="currency_id")
    net_amount = fields.Monetary(string="Neto (alias)", compute="_compute_alias", store=False, currency_field="currency_id")
    gross_amount = fields.Monetary(string="Bruto (alias)", compute="_compute_alias", store=False, currency_field="currency_id")

    @api.depends("grain_grade", "amount_untaxed", "amount_tax", "amount_total")
    def _compute_alias(self):
        for rec in self:
            rec.grade = rec.grain_grade
            rec.subtotal = rec.amount_untaxed
            rec.tax_amount = rec.amount_tax
            rec.total = rec.amount_total
            rec.net_amount = rec.amount_untaxed
            rec.gross_amount = rec.amount_total

    @api.depends("qty_kg", "price_per_kg")
    def _compute_tn_price(self):
        for rec in self:
            rec.qty_tn = (rec.qty_kg or 0.0) / 1000.0
            rec.price_per_tn = (rec.price_per_kg or 0.0) * 1000.0

    @api.depends("qty_kg", "price_per_kg", "tax_id", "currency_id")
    def _compute_amounts(self):
        for rec in self:
            base = (rec.qty_kg or 0.0) * (rec.price_per_kg or 0.0)
            rec.amount_untaxed = base
            rec.amount_tax = 0.0
            rec.amount_total = base
            if rec.tax_id:
                taxes = rec.tax_id.compute_all(
                    base, currency=rec.currency_id, quantity=1.0,
                    product=False, partner=rec.producer_id
                )
                rec.amount_tax = taxes["total_included"] - taxes["total_excluded"]
                rec.amount_total = taxes["total_included"]

    def _get_outbound_method_line(self, journal):
        pml = journal.outbound_payment_method_line_ids[:1]
        if not pml:
            raise UserError(_("El diario '%s' no tiene método de pago SALIENTE configurado.") % journal.display_name)
        return pml[0]

    def action_create_lsg(self):
        self.ensure_one()

        if self.amount_total <= 0:
            raise UserError(_("El total es 0. Verifique cantidad y precio."))

        if not self.journal_id:
            raise UserError(_("Configurá el Diario de Pago (LSG)."))

        # 1) Crear liquidación LSG (documento funcional)
        liquidation = self.env["grain.liquidation"].create({
            "date": self.date,
            "liquidation_type": "lsg",
            "company_id": self.company_id.id,
            "coe": self.coe,
            "producer_id": self.producer_id.id,
            "broker_id": self.broker_id.id,
            "product_id": self.product_id.id,
            "delivery_date": self.delivery_date,
            "port": self.port,
            "grain_grade": self.grain_grade,
            "qty_tn": self.qty_tn,
            "price_per_tn": self.price_per_tn,
            "tax_id": self.tax_id.id if self.tax_id else False,
            # dejamos estos por consistencia (aunque el pago usa journal_id)
            "clearing_account_id": self.clearing_account_id.id if self.clearing_account_id else False,
            "journal_id": self.company_id.grain_liquidation_journal_id.id or False,
            "state": "draft",
        })

        # 2) Crear PAGO saliente (sin factura) para que luego se aplique desde la factura de proveedor
        journal = self.journal_id
        method_line = self._get_outbound_method_line(journal)

        ref = ("LSG %s%s" % (self.coe + " " if self.coe else "", liquidation.name or "")).strip()

        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.producer_id.commercial_partner_id.id,
            "amount": self.amount_total,
            "currency_id": self.currency_id.id,
            "date": self.date,
            "journal_id": journal.id,
            "payment_method_line_id": method_line.id,
            "ref": ref,
        })
        payment.action_post()

        # Linkeo para trazabilidad
        liquidation.write({
            "payment_id": payment.id,
            "move_id": payment.move_id.id,
            "state": "posted",
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("LSG"),
            "res_model": "grain.liquidation",
            "res_id": liquidation.id,
            "view_mode": "form",
            "target": "current",
        }
