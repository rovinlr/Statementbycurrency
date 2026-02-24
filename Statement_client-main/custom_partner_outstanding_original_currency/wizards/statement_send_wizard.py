from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StatementSendWizard(models.TransientModel):
    _name = "statement.send.wizard"
    _description = "Enviar estado de cuenta"

    partner_id = fields.Many2one("res.partner", required=True)
    email_to = fields.Char(string="Para")
    email_cc = fields.Char(string="CC")
    subject = fields.Char(required=True)
    body = fields.Html(string="Contenido", sanitize_style=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        partner = self.env["res.partner"].browse(values.get("partner_id") or self.env.context.get("default_partner_id"))
        if partner:
            targets = partner._get_statement_target_emails()
            values.setdefault("email_to", targets["email_to"])
            values.setdefault("email_cc", targets["email_cc"])
            values.setdefault("subject", _("Estado de cuenta - %(partner)s") % {"partner": partner.name})
            values.setdefault(
                "body",
                _(
                    """
                    <p>Dear Sir or Madam, %(partner)s,</p>
                    <p>Please find attached your account statement. If you have any questions, please do not hesitate to contact us.</p>
                    <p>Best regards.</p>
                    """
                )
                % {"partner": partner.name},
            )
        return values


    def _validate_target_emails(self):
        self.ensure_one()
        targets = self.partner_id._get_statement_target_emails()
        if not targets["email_to"]:
            raise UserError(_('El contacto no tiene configurado un correo en "Correo para estados de cuenta".'))

    def action_send_statement(self):
        self.ensure_one()
        self._validate_target_emails()
        targets = self.partner_id._get_statement_target_emails()
        attachment = self.partner_id._render_statement_report_pdf()
        mail = self.env["mail.mail"].create(
            {
                "subject": self.subject,
                "body_html": self.body or "",
                "email_to": targets["email_to"],
                "email_cc": targets["email_cc"],
                "attachment_ids": [(4, attachment.id)],
                "auto_delete": False,
            }
        )
        mail.send()
        return {"type": "ir.actions.act_window_close"}
