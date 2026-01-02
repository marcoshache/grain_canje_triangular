from odoo import models, fields, api
from odoo.exceptions import UserError


class ApplyGrainCanjeWizard(models.TransientModel):
    _name = "apply.grain.canje.wizard"
    _description = "Aplicar Canje de Granos"

    move_id = fields.Many2one("account.move", required=True)
    supplier_id = fields.Many2one("res.partner", required=True)
    contract_id = fields.Many2one(
        "grain.canje.contract",
        required=True,
        domain="[('state','=','open'), ('supplier_id','=',supplier_id)]"
    )
    tn_disponibles = fields.Float(related="contract_id.tn_disponibles", readonly=True)
    tn_aplicar = fields.Float(string="TN a aplicar", required=True)
    amount_equivalent = fields.Float(string="Monto equivalente", compute="_compute_amount")

    def _compute_amount(self):
        for w in self:
            w.amount_equivalent = w.tn_aplicar * w.contract_id.precio_ref

    def action_apply(self):
        self.ensure_one()

        contract = self.contract_id
        move = self.move_id
        company = self.env.company

        # Validaciones
        if self.tn_aplicar > contract.tn_disponibles:
            raise UserError("Las TN a aplicar superan las disponibles.")

        if move.state != "posted":
            raise UserError("La factura debe estar publicada para aplicar canje.")

        # Obtener parámetros contables
        journal = company.canje_journal_id
        cuenta_cte_prod = company.canje_account_id

        if not journal or not cuenta_cte_prod:
            raise UserError("Configurar diario y cuenta de canje en Ajustes → Contabilidad.")

        # 1) Registrar aplicación
        app = self.env["grain.canje.application"].create({
            "contract_id": contract.id,
            "move_id": move.id,
            "date": fields.Date.today(),
            "tn_aplicadas": self.tn_aplicar,
            "amount": self.amount_equivalent,
        })

        # 2) Crear asiento contable automático
        asiento = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": fields.Date.today(),
            "ref": f"Canje {contract.name} aplicado a {move.name}",
            "line_ids": [
                # Debe proveedor
                (0, 0, {
                    "account_id": move.line_ids.filtered(lambda l: l.credit > 0).account_id.id,
                    "partner_id": move.partner_id.id,
                    "debit": self.amount_equivalent,
                }),
                # Haber cuenta corriente cereal
                (0, 0, {
                    "account_id": cuenta_cte_prod.id,
                    "partner_id": contract.producer_id.id,
                    "credit": self.amount_equivalent,
                }),
            ]
        })
        asiento.action_post()

        # 3) Conciliar asiento con factura
        lines_prov = move.line_ids.filtered(lambda l: l.account_id == asiento.line_ids[0].account_id)
        lines_asiento = asiento.line_ids.filtered(lambda l: l.account_id == lines_prov[0].account_id)

        (lines_prov + lines_asiento).reconcile()

        return {"type": "ir.actions.act_window_close"}
