# -*- coding: utf-8 -*-
from odoo import api, fields, models

class RegisterGrainLSGWizard(models.TransientModel):
    _inherit = "register.grain.lsg.wizard"

    # Compat: algunas vistas usan "grade" en vez de "grain_grade"
    grade = fields.Char(string="Grado", compute="_compute_grade", inverse="_inverse_grade")

    @api.depends("grain_grade")
    def _compute_grade(self):
        for rec in self:
            rec.grade = rec.grain_grade

    def _inverse_grade(self):
        for rec in self:
            rec.grain_grade = rec.grade
