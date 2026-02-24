import base64
import json
from collections.abc import Mapping

from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    statement_email = fields.Char(string="Correo para estados de cuenta")
    statement_email_cc = fields.Char(string="CC para estados de cuenta")

    def _get_statement_report(self):
        return self.env.ref(
            "custom_partner_outstanding_original_currency.account_report_estado_cuenta_por_cobrar_moneda_original"
        )

    def _get_statement_report_options(self):
        self.ensure_one()
        report = self._get_statement_report()
        # account.report.get_options() expects a dict in newer account_reports
        # versions; passing None raises an AttributeError when it calls .get().
        options = report.get_options(previous_options={})
        partner_id = str(self.id)
        options["partner_ids"] = [partner_id]
        # account_reports PDF filter template joins selected values as strings.
        # Keeping ids as strings avoids `TypeError: expected str instance, int found`.
        options["selected_partner_ids"] = [partner_id]
        options["partner"] = [{"id": self.id, "name": self.display_name, "selected": True}]
        options["unfold_all"] = True
        return options

    def action_open_statement_report(self):
        self.ensure_one()
        report = self._get_statement_report()
        options = self._get_statement_report_options()
        return {
            "type": "ir.actions.client",
            "name": report.name,
            "tag": "account_report",
            "context": {
                "report_id": report.id,
                "options": json.dumps(options),
                "unfold_all": True,
                "active_model": "res.partner",
                "active_id": self.id,
                "default_partner_ids": [self.id],
                "statement_partner_ids": [self.id],
            },
        }


    def _get_statement_target_emails(self):
        self.ensure_one()
        email_to = (self.statement_email or "").strip()
        email_cc = (self.statement_email_cc or "").strip()
        return {
            "email_to": email_to,
            "email_cc": email_cc,
        }

    def _get_followup_mail_recipients(self):
        """Extension hook for account_followup: prefer statement email fields."""
        self.ensure_one()
        recipients = super()._get_followup_mail_recipients() if hasattr(super(), "_get_followup_mail_recipients") else {}
        target = self._get_statement_target_emails()
        recipients.update({
            "email_to": target["email_to"],
            "email_cc": target["email_cc"],
        })
        return recipients

    def action_send_statement_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Enviar estado de cuenta"),
            "res_model": "statement.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.id,
            },
        }

    def _get_statement_pdf_filename(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        return _("Estado_de_Cuenta_%(partner)s_%(date)s.pdf") % {
            "partner": self.name.replace("/", "-") if self.name else self.id,
            "date": today,
        }

    def _render_statement_report_pdf(self):
        self.ensure_one()
        report = self._get_statement_report().with_company(self.company_id)
        options = self._get_statement_report_options()

        if hasattr(report, "export_to_pdf"):
            pdf_data = report.export_to_pdf(options)
        elif hasattr(report, "get_pdf"):
            pdf_data = report.get_pdf(options)
        elif hasattr(report, "_get_pdf"):
            pdf_data = report._get_pdf(options)
        else:
            raise AttributeError(_("El reporte contable no soporta exportación a PDF en esta versión."))

        if isinstance(pdf_data, tuple):
            pdf_data = pdf_data[0]

        if isinstance(pdf_data, Mapping):
            pdf_data = (
                pdf_data.get("file_content")
                or pdf_data.get("datas")
                or pdf_data.get("data")
                or pdf_data.get("content")
            )

        if isinstance(pdf_data, str):
            try:
                pdf_data = base64.b64decode(pdf_data)
            except Exception:
                pdf_data = pdf_data.encode()

        if not isinstance(pdf_data, (bytes, bytearray)):
            raise TypeError(
                _("No se pudo generar el PDF del estado de cuenta. Se recibió un tipo de dato no compatible.")
            )

        attachment = self.env["ir.attachment"].create(
            {
                "name": self._get_statement_pdf_filename(),
                "type": "binary",
                "datas": base64.b64encode(pdf_data),
                "mimetype": "application/pdf",
                "res_model": "res.partner",
                "res_id": self.id,
                "company_id": self.company_id.id,
            }
        )
        return attachment
