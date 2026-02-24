from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    fp_consecutive_number = fields.Char(string="Consecutive Number")
