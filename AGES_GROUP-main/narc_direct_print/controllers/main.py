import base64

from odoo import http
from odoo.http import request

from .qz_sign import certificate_pem, sign_request
from .setup_scripts import LINUX_SETUP_SH, WINDOWS_SETUP_BAT, WINDOWS_SETUP_PS1

_CONTEXT_KEYS = (
    "lang",
    "tz",
    "uid",
    "allowed_company_ids",
    "active_id",
    "active_ids",
    "active_model",
)


class ReportDirectPrintController(http.Controller):
    @http.route("/report/direct_print/pdf", type="json", auth="user")
    def direct_print_pdf(self, report_name, docids=None, data=None, context=None, **kwargs):
        """Render a report as PDF so the browser can send it to the local printer."""
        report_env = request.env["ir.actions.report"]
        safe_context = self._safe_context(context)
        if safe_context:
            report_env = report_env.with_context(**safe_context)

        report = report_env._get_report(report_name)
        res_ids = docids or None
        payload = data or {}

        if report.report_type == "qweb-text":
            content = report_env._render_qweb_text(report_name, res_ids, data=payload)[0]
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            return {"text": content, "name": report.name or "Report"}

        pdf = report_env._render_qweb_pdf(report_name, res_ids=res_ids, data=payload)[0]
        return {
            "pdf_base64": base64.b64encode(pdf).decode(),
            "name": report.name or "Report",
        }

    def _safe_context(self, context):
        if not isinstance(context, dict):
            return {}
        return {key: context[key] for key in _CONTEXT_KEYS if key in context}

    @http.route("/narc_direct_print/qz/certificate", type="http", auth="public", csrf=False)
    def qz_certificate(self, download=None, **kwargs):
        headers = [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Cache-Control", "no-store"),
        ]
        if download:
            headers.append(
                ("Content-Disposition", "attachment; filename=override.crt")
            )
        return request.make_response(certificate_pem(), headers=headers)

    @http.route("/narc_direct_print/qz/sign", type="json", auth="user")
    def qz_sign(self, to_sign=None, **kwargs):
        return sign_request(to_sign or "")

    def _setup_base_url(self):
        return request.httprequest.url_root.rstrip("/")

    def _setup_db_name(self):
        return getattr(request, "db", None) or (
            request.env.cr.dbname if request.env else ""
        )

    def _filled_setup_script(self, template):
        cert = certificate_pem().strip() + "\n"
        return (
            template
            .replace("__BASE_URL__", self._setup_base_url())
            .replace("__DB_NAME__", self._setup_db_name() or "")
            .replace("__CERT_B64__", base64.b64encode(cert.encode("utf-8")).decode("ascii"))
        )

    def _setup_file(self, body, content_type, filename):
        return request.make_response(
            body,
            headers=[
                ("Content-Type", content_type),
                ("Content-Disposition", f"attachment; filename={filename}"),
                ("Cache-Control", "no-store"),
            ],
        )

    @http.route(
        ["/narc_direct_print/qz/setup.ps1", "/narc_direct_print/qz/setup-script"],
        type="http",
        auth="public",
        csrf=False,
    )
    def qz_setup_ps1(self, **kwargs):
        script = self._filled_setup_script(WINDOWS_SETUP_PS1)
        return self._setup_file(script, "text/plain; charset=utf-8", "narc-print-setup.ps1")

    @http.route("/narc_direct_print/qz/setup.bat", type="http", auth="public", csrf=False)
    def qz_setup_bat(self, **kwargs):
        ps1 = self._filled_setup_script(WINDOWS_SETUP_PS1)
        payload = base64.b64encode(ps1.encode("utf-8")).decode("ascii")
        script = WINDOWS_SETUP_BAT.replace("__PS1_B64__", payload)
        return self._setup_file(
            script, "application/octet-stream", "narc-print-setup.bat"
        )

    @http.route("/narc_direct_print/qz/setup.sh", type="http", auth="public", csrf=False)
    def qz_setup_sh(self, **kwargs):
        script = self._filled_setup_script(LINUX_SETUP_SH)
        return self._setup_file(script, "application/x-sh", "narc-print-setup.sh")
