# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools.float_utils import float_round


class GrainCanjeCampaign(models.Model):
    _name = "grain.canje.campaign"
    _description = "Campaña de canje de granos"

    name = fields.Char(string="Nombre campaña", required=True)
    date_start = fields.Date(string="Desde")
    date_end = fields.Date(string="Hasta")
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        default=lambda self: self.env.company,
        required=True,
    )


class GrainCanjeContract(models.Model):
    _name = "grain.canje.contract"
    _description = "Contrato de canje de granos"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="N° Contrato",
        required=True,
        copy=False,
        tracking=True,
    )
    date = fields.Date(
        string="Fecha contrato",
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        default=lambda self: self.env.company,
        required=True,
    )
    campaign_id = fields.Many2one(
        "grain.canje.campaign",
        string="Campaña",
        tracking=True,
    )

    producer_id = fields.Many2one(
        "res.partner",
        string="Productor",
        required=True,
        tracking=True,
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="Proveedor de insumos",
        required=True,
        tracking=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Grano",
        required=True,
        tracking=True,
    )

    # TN pactadas manualmente (opcional, por contrato)
    tn_pactadas = fields.Float(
        string="TN pactadas",
        tracking=True,
    )
    # Movimientos MRV vinculados (stock.move)
    stock_move_ids = fields.Many2many(
        "stock.move",
        "grain_canje_contract_move_rel",
        "contract_id",
        "move_id",
        string="Movimientos MRV",
        domain=[("state", "=", "done")],
    )
    tn_mrv = fields.Float(
        string="TN desde MRV",
        compute="_compute_tn_mrv",
        store=True,
    )

    tn_aplicadas = fields.Float(
        string="TN aplicadas",
        compute="_compute_tn_aplicadas",
        store=True,
    )
    tn_disponibles = fields.Float(
        string="TN disponibles",
        compute="_compute_tn_disponibles",
        store=True,
    )

    precio_ref = fields.Float(
        string="Precio referencia por TN",
        tracking=True,
    )

    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("open", "Vigente"),
            ("done", "Cerrado"),
            ("cancel", "Cancelado"),
        ],
        default="draft",
        tracking=True,
    )

    application_ids = fields.One2many(
        "grain.canje.application",
        "contract_id",
        string="Aplicaciones",
    )

    _sql_constraints = [
        (
            "tn_pactadas_non_negative",
            "CHECK(tn_pactadas >= 0)",
            "Las toneladas pactadas deben ser mayores o iguales a cero.",
        )
    ]

    @api.depends("stock_move_ids", "stock_move_ids.product_uom_qty")
    def _compute_tn_mrv(self):
        """Suma de TN desde movimientos de stock vinculados (MRV)."""
        for contract in self:
            total = 0.0
            for move in contract.stock_move_ids:
                qty = move.product_uom_qty
                # Convertir a la UoM del producto del contrato si aplica
                if contract.product_id and move.product_uom and contract.product_id.uom_id:
                    qty = move.product_uom._compute_quantity(
                        move.product_uom_qty,
                        contract.product_id.uom_id,
                    )
                total += qty
            contract.tn_mrv = float_round(total, precision_digits=3)

    @api.depends("application_ids", "application_ids.tn_aplicadas")
    def _compute_tn_aplicadas(self):
        for contract in self:
            contract.tn_aplicadas = float_round(
                sum(contract.application_ids.mapped("tn_aplicadas")),
                precision_digits=3,
            )

    @api.depends("tn_pactadas", "tn_mrv", "tn_aplicadas")
    def _compute_tn_disponibles(self):
        """Base = tn_pactadas si se cargó; sino, tn_mrv."""
        for contract in self:
            base = contract.tn_pactadas or contract.tn_mrv
            contract.tn_disponibles = float_round(
                base - contract.tn_aplicadas,
                precision_digits=3,
            )

    def action_open(self):
        self.write({"state": "open"})

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})


class GrainCanjeApplication(models.Model):
    _name = "grain.canje.application"
    _description = "Aplicación de canje de granos a factura de proveedor"
    _order = "date desc, id desc"

    contract_id = fields.Many2one(
        "grain.canje.contract",
        string="Contrato",
        required=True,
        ondelete="cascade",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Factura proveedor",
        required=True,
        domain=[("move_type", "=", "in_invoice")],
        ondelete="cascade",
    )
    date = fields.Date(
        string="Fecha de aplicación",
        default=fields.Date.context_today,
    )
    tn_aplicadas = fields.Float(
        string="TN aplicadas",
        required=True,
    )
    amount = fields.Monetary(
        string="Monto equivalente",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="move_id.currency_id",
        store=True,
        readonly=True,
    )

    # Campos para reportes / pivot
    producer_id = fields.Many2one(
        "res.partner",
        string="Productor",
        related="contract_id.producer_id",
        store=True,
        readonly=True,
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        related="contract_id.supplier_id",
        store=True,
        readonly=True,
    )
    campaign_id = fields.Many2one(
        "grain.canje.campaign",
        string="Campaña",
        related="contract_id.campaign_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Grano",
        related="contract_id.product_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="contract_id.company_id",
        store=True,
        readonly=True,
    )

    @api.depends("tn_aplicadas", "contract_id.precio_ref")
    def _compute_amount(self):
        for app in self:
            app.amount = (app.tn_aplicadas or 0.0) * (app.contract_id.precio_ref or 0.0)
