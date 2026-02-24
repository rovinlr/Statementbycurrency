from collections import defaultdict

from odoo import _, fields, models
from odoo.tools.misc import formatLang
from odoo.tools import float_is_zero


class OutstandingOriginalCurrencyReportHandler(models.AbstractModel):
    _name = "account.outstanding.original.currency.report.handler"
    _inherit = "account.report.custom.handler"
    _description = "Outstanding Receivable in Original Currency Report Handler"
    _COLUMN_EXPRESSIONS = ("fecha", "fecha_vencimiento", "importe_original", "saldo")

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        self._apply_context_partner_filter(options)
        options.setdefault("unfold_all", False)
        self._sync_column_labels(report, options)

    def _sync_column_labels(self, report, options):
        """Keep Odoo's header metadata intact and only fill visible labels."""
        ordered_columns = report.column_ids.sorted("sequence")
        if not ordered_columns:
            return

        labels_by_expression = {
            column.expression_label: column.name
            for column in ordered_columns
            if column.expression_label
        }
        ordered_labels = [column.name for column in ordered_columns]

        for index, column in enumerate(options.get("columns", [])):
            label = labels_by_expression.get(column.get("expression_label"))
            if not label and index < len(ordered_labels):
                label = ordered_labels[index]
            if label:
                column["name"] = label

        column_headers = options.get("column_headers") or []
        for row in column_headers:
            for cell in row:
                label = labels_by_expression.get(cell.get("expression_label"))
                if label:
                    cell["name"] = label

        # Some Odoo 19 builds provide leaf header cells without expression_label.
        # The leaf row is the last header row, but it can include fewer cells than
        # report columns when column groups are active.
        if not column_headers:
            return

        leaf_row = column_headers[-1]
        labels_to_apply = ordered_labels[-len(leaf_row) :]
        start_index = len(leaf_row) - len(labels_to_apply)

        for index, label in enumerate(labels_to_apply):
            header_index = start_index + index
            if not leaf_row[header_index].get("name"):
                leaf_row[header_index]["name"] = label

    def _apply_context_partner_filter(self, options):
        context = self.env.context
        context_partner_ids = context.get("statement_partner_ids") or context.get("default_partner_ids") or []
        if isinstance(context_partner_ids, int):
            context_partner_ids = [context_partner_ids]

        if not context_partner_ids and context.get("active_model") == "res.partner" and context.get("active_id"):
            context_partner_ids = [context["active_id"]]

        partner_ids = [int(pid) for pid in context_partner_ids if pid]
        if not partner_ids:
            return

        partners = self.env["res.partner"].browse(partner_ids)
        options["partner_ids"] = partner_ids
        # Keep the partner filter for querying, but avoid exposing internal IDs in the PDF header.
        options["selected_partner_ids"] = []
        options["partner"] = [{"id": partner.id, "name": partner.display_name, "selected": True} for partner in partners]

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        grouped_results = self._get_grouped_moves(options)
        lines = []

        unfolded_lines = set(options.get("unfolded_lines", []))
        unfold_all = options.get("unfold_all")

        for partner_key in sorted(grouped_results.keys(), key=lambda key: (key[1] or "").lower()):
            partner_id, partner_name = partner_key
            partner_payload = grouped_results[partner_key]
            partner_line_id = report._get_generic_line_id("res.partner", partner_id, markup="partner")
            partner_is_unfolded = unfold_all or partner_line_id in unfolded_lines

            lines.append(
                {
                    "id": partner_line_id,
                    "name": partner_name or _("No Partner"),
                    "level": 1,
                    "unfoldable": True,
                    "unfolded": bool(partner_is_unfolded),
                    "class": "o_statement_original_currency_partner",
                    "columns": self._empty_columns(),
                }
            )

            if not partner_is_unfolded:
                continue

            for currency_id, currency_data in sorted(
                partner_payload.items(), key=lambda item: (item[1]["currency_name"] or "")
            ):
                currency = self.env["res.currency"].browse(currency_id)
                currency_line_id = report._get_generic_line_id(
                    "res.currency", currency_id, parent_line_id=partner_line_id, markup="currency"
                )
                currency_is_unfolded = unfold_all or currency_line_id in unfolded_lines

                lines.append(
                    {
                        "id": currency_line_id,
                        "parent_id": partner_line_id,
                        "name": currency_data["currency_name"],
                        "level": 2,
                        "unfoldable": True,
                        "unfolded": bool(currency_is_unfolded),
                        "class": "o_statement_original_currency_currency",
                        "columns": self._empty_columns(),
                    }
                )

                if not currency_is_unfolded:
                    continue

                for move in currency_data["moves"]:
                    lines.append(
                        {
                            "id": report._get_generic_line_id("account.move", move["id"], parent_line_id=currency_line_id),
                            "parent_id": currency_line_id,
                            "name": move["display_number"],
                            "level": 3,
                            "caret_options": "account.move",
                            "class": "o_statement_original_currency_detail",
                            "columns": [
                                {
                                    "name": self._fmt_date(move["invoice_date"]),
                                    "expression_label": "fecha",
                                },
                                {
                                    "name": self._fmt_date(move["invoice_date_due"]),
                                    "expression_label": "fecha_vencimiento",
                                },
                                {
                                    "expression_label": "importe_original",
                                    **self._monetary_col(report, move["original_amount"], currency),
                                },
                                {
                                    "expression_label": "saldo",
                                    **self._monetary_col(report, move["residual_amount"], currency),
                                },
                            ],
                        }
                    )

                lines.append(
                    {
                        "id": report._get_generic_line_id("res.currency", currency_id, parent_line_id=currency_line_id, markup="subtotal"),
                        "parent_id": currency_line_id,
                        "name": _("Subtotal"),
                        "level": 3,
                        "class": "o_statement_original_currency_subtotal",
                        "columns": [
                            {"name": "", "expression_label": "fecha"},
                            {"name": "", "expression_label": "fecha_vencimiento"},
                            {
                                "expression_label": "importe_original",
                                **self._monetary_col(report, currency_data["subtotal_original"], currency),
                            },
                            {
                                "expression_label": "saldo",
                                **self._monetary_col(report, currency_data["subtotal_residual"], currency),
                            },
                        ],
                    }
                )

        return [(0, line) for line in lines]

    def _empty_columns(self):
        return [{"name": "", "expression_label": expression} for expression in self._COLUMN_EXPRESSIONS]

    def _report_custom_engine_outstanding_original_currency(self, *args, **kwargs):
        """Placeholder to expose editable expression rows in report configuration."""
        return {}

    def _get_grouped_moves(self, options):
        moves = self.env["account.move"].search(
            self._get_moves_domain(options),
            order="partner_id, currency_id, invoice_date, id",
        )

        partner_currency_map = defaultdict(dict)
        for move in moves:
            currency = move.currency_id
            residual_amount = move.amount_residual
            if float_is_zero(residual_amount, precision_rounding=currency.rounding):
                continue

            partner_key = (move.partner_id.id, move.partner_id.name or _("No Partner"))
            currency_id = currency.id
            if currency_id not in partner_currency_map[partner_key]:
                partner_currency_map[partner_key][currency_id] = {
                    "currency_name": currency.name,
                    "subtotal_original": 0.0,
                    "subtotal_residual": 0.0,
                    "moves": [],
                }

            sign = -1 if move.move_type == "out_refund" else 1
            original_amount = sign * move.amount_total
            residual_amount = sign * residual_amount

            partner_currency_map[partner_key][currency_id]["subtotal_original"] += original_amount
            partner_currency_map[partner_key][currency_id]["subtotal_residual"] += residual_amount
            partner_currency_map[partner_key][currency_id]["moves"].append(
                {
                    "id": move.id,
                    "invoice_date": move.invoice_date,
                    "invoice_date_due": move.invoice_date_due,
                    "display_number": move.fp_consecutive_number or move.name,
                    "original_amount": original_amount,
                    "residual_amount": residual_amount,
                }
            )

        for partner_data in partner_currency_map.values():
            for currency_payload in partner_data.values():
                currency_payload["moves"].sort(
                    key=lambda move: (move["invoice_date"] or fields.Date.to_date("1900-01-01"), move["id"])
                )

        return partner_currency_map

    def _get_moves_domain(self, options):
        domain = [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("amount_residual", "!=", 0.0),
            ("company_id", "in", self.env.companies.ids),
        ]

        date_options = options.get("date") or {}
        date_from = date_options.get("date_from")
        date_to = date_options.get("date_to")
        if date_from:
            domain.append(("invoice_date", ">=", date_from))
        if date_to:
            domain.append(("invoice_date", "<=", date_to))

        selected_journal_ids = [
            journal.get("id")
            for journal in (options.get("journals") or [])
            if journal.get("id") and journal.get("selected")
        ]
        if selected_journal_ids:
            domain.append(("journal_id", "in", selected_journal_ids))

        partner_ids = self._extract_partner_ids(options)
        if partner_ids:
            domain.append(("partner_id", "in", partner_ids))
        return domain

    def _extract_partner_ids(self, options):
        partner_ids = options.get("partner_ids") or []
        if isinstance(partner_ids, str):
            parsed_partner_ids = []
            for partner_id in partner_ids.split(","):
                partner_id = (partner_id or "").strip()
                if not partner_id:
                    continue
                if partner_id.isdigit():
                    parsed_partner_ids.append(int(partner_id))
            return parsed_partner_ids

        result = []
        for partner_id in partner_ids:
            if isinstance(partner_id, (list, tuple)):
                partner_id = partner_id[0]
            if partner_id:
                result.append(int(partner_id))

        if result:
            return result

        partner_filter_values = options.get("partner")
        if isinstance(partner_filter_values, dict):
            partner_filter_values = [partner_filter_values]
        elif not isinstance(partner_filter_values, (list, tuple)):
            partner_filter_values = []
        filter_partner_ids = [
            int(partner.get("id"))
            for partner in partner_filter_values
            if isinstance(partner, dict) and partner.get("id") and partner.get("selected")
        ]
        if filter_partner_ids:
            return filter_partner_ids

        selected_partner_ids = options.get("selected_partner_ids") or []
        return [int(pid) for pid in selected_partner_ids if pid]

    def _monetary_col(self, report, amount, currency):
        amount = currency.round(amount or 0.0)
        return {
            "name": formatLang(self.env, amount, currency_obj=currency),
            "no_format": amount,
            "figure_type": "monetary",
            "currency_id": currency.id,
            "class": "number",
        }

    def _fmt_date(self, date_value):
        return date_value.strftime("%d/%m/%Y") if date_value else ""
