{
    "name": "Estado de cuenta por cobrar (Moneda original)",
    "summary": "Reporte dinámico de cuentas por cobrar por cliente y moneda original",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "license": "LGPL-3",
    "author": "FenixCR Solutions",
    "depends": ["base", "account", "account_reports", "mail", "account_followup"],
    "assets": {
        "web.report_assets_common": [
            "custom_partner_outstanding_original_currency/static/src/scss/account_report_original_currency.scss",
        ],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/account_report.xml",
        "views/res_partner_views.xml",
        "views/statement_send_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
