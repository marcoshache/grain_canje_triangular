# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApplyGrainCanjeWizard(models.TransientModel):
    _name = "apply.grain.canje.wizard"
    _description = "Wizard para aplicar canje de granos a factura de proveedor"

    contract_id = fields.Many2one(
        "grain.canje.contract",
        string="Contrato de canje",
        required=True,
        domain="[('state', '=', 'open'), "
               " ('supplier_id', '=', supplier_id), "
               " ('company_id', '=', company_id)]",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Factura proveedor",
        required=True,
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted')]",
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="Proveedor de insumos",
        related="move_id.partner_id",
        store=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="move_id.company_id",
        store=True,
        readonly=True,
    )
    tn_disponibles = fields.Float(
        string="TN disponibles",
        related="contract_id.tn_disponibles",
        readonly=True,
    )
    tn_aplicar = fields.Float(
        string="TN a aplicar",
        required=True,
    )
    amount = fields.Monetary(
        string="Monto equivalente",
        currency_field="currency_id",
        compute="_compute_amount",
        store=False,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="move_id.currency_id",
        readonly=True,
    )

    # ------------------------------
    # HELPERS
    # ------------------------------

    @api.depends("tn_aplicar", "contract_id.precio_ref")
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = (wizard.tn_aplicar or 0.0) * (wizard.contract_id.precio_ref or 0.0)

    @api.model
    def default_get(self, fields_list):
        """Pre-cargar la factura activa en el wizard."""
        res = super().default_get(fields_list)
        move_id = self.env.context.get("active_id")
        if move_id and "move_id" in fields_list:
            res["move_id"] = move_id
        return res

    # ------------------------------
    # ACCIÓN PRINCIPAL
    # ------------------------------

    def action_apply(self):
        self.ensure_one()

        contract = self.contract_id
        move = self.move_id
        company = move.company_id
        company_currency = company.currency_id

        # --- Validaciones básicas ---
        if self.tn_aplicar <= 0.0:
            raise UserError(_("Las toneladas a aplicar deben ser mayores a cero."))

        if self.tn_aplicar > (contract.tn_disponibles or 0.0) + 1e-6:
            raise UserError(_("Las TN a aplicar superan las disponibles en el contrato."))

        if move.state != "posted":
            raise UserError(_("La factura debe estar publicada para aplicar el canje."))

        # --- Config contable de canje ---
        journal = company.canje_journal_id
        cuenta_cte_prod = company.canje_account_id
        if not journal or not cuenta_cte_prod:
            raise UserError(_("Configurar diario y cuenta de canje en Ajustes → Contabilidad."))

        # --- Monto del canje en moneda de la factura ---
        amount_inv_cur = self.amount
        if amount_inv_cur <= 0.0:
            raise UserError(_("El monto equivalente debe ser mayor que cero."))

        # --- Saldo pendiente de la factura en moneda de la factura ---
        if move.currency_id == company_currency:
            # Factura en moneda de la compañía
            residual_inv_cur = abs(move.amount_residual)
        else:
            # Factura en moneda extranjera:
            # tomamos las líneas de proveedor y sumamos amount_residual_currency
            vendor_lines_for_residual = move.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            )
            residual_inv_cur = abs(sum(vendor_lines_for_residual.mapped("amount_residual_currency")))

        if amount_inv_cur > residual_inv_cur + 0.01:
            raise UserError(
                _(
                    "No podés aplicar más que el saldo pendiente de la factura.\n"
                    "Saldo actual: %(saldo).2f %(moneda)s"
                )
                % {
                    "saldo": residual_inv_cur,
                    "moneda": move.currency_id.name,
                }
            )

        # --- Monto en moneda de la compañía (ARS) ---
        amount_company_cur = move.currency_id._convert(
            amount_inv_cur,
            company_currency,
            company,
            move.invoice_date or fields.Date.context_today(self),
        )

        # --------------------------
        # 1) Registrar aplicación
        # --------------------------
        application = self.env["grain.canje.application"].create(
            {
                "contract_id": contract.id,
                "move_id": move.id,
                "date": fields.Date.context_today(self),
                "tn_aplicadas": self.tn_aplicar,
                "amount": amount_inv_cur,
            }
        )

        # --------------------------
        # 2) Crear asiento contable
        # --------------------------

        # Localizar línea de proveedor de la factura (no reconciliada)
        vendor_lines = move.line_ids.filtered(
            lambda l: l.account_id.account_type == "liability_payable" and not l.reconciled
        )
        if not vendor_lines:
            raise UserError(
                _("No se encontró una línea de proveedor pendiente de conciliar en la factura.")
            )

        vendor_account = vendor_lines[0].account_id

        move_canje = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": move.invoice_date or fields.Date.context_today(self),
                "journal_id": journal.id,
                "ref": _("Canje %s aplicado a %s") % (contract.name, move.name),
                "line_ids": [
                    # Debe: cuenta proveedor (reduce deuda)
                    (
                        0,
                        0,
                        {
                            "account_id": vendor_account.id,
                            "partner_id": move.partner_id.id,
                            "debit": amount_company_cur,
                            "credit": 0.0,
                            "currency_id": move.currency_id.id,
                            "amount_currency": amount_inv_cur,  # en moneda de la factura (USD, etc.)
                        },
                    ),
                    # Haber: Cta Cte Cereal Productor (deuda con productor)
                    (
                        0,
                        0,
                        {
                            "account_id": cuenta_cte_prod.id,
                            "partner_id": contract.producer_id.id,
                            "debit": 0.0,
                            "credit": amount_company_cur,
                            "currency_id": move.currency_id.id,
                            "amount_currency": -amount_inv_cur,
                        },
                    ),
                ],
            }
        )
        move_canje.action_post()

        # --------------------------
        # 3) Conciliar con la factura
        # --------------------------
        canje_vendor_lines = move_canje.line_ids.filtered(
            lambda l: l.account_id.id == vendor_account.id
            and l.partner_id.id == move.partner_id.id
        )

        (vendor_lines + canje_vendor_lines).reconcile()

        # --------------------------
        # 4) Mensaje en la factura
        # --------------------------
        move.message_post(
            body=_(
                "Aplicación de canje de granos:\n"
                "- Contrato: %(contract)s\n"
                "- TN aplicadas: %(tn).2f\n"
                "- Monto equivalente: %(amount).2f %(currency)s"
            )
            % {
                "contract": contract.name,
                "tn": self.tn_aplicar,
                "amount": amount_inv_cur,
                "currency": move.currency_id.name,
            }
        )

        return {"type": "ir.actions.act_window_close"}
