from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_cr_document_id = fields.Char(string="Consecutive Number")
