/** @odoo-module **/

import { actionService } from "@web/webclient/actions/action_service";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ReportAction } from "@web/webclient/actions/reports/report_action";

const QZ_SCRIPT_URL = "/narc_direct_print/static/lib/qz-tray/qz-tray.js";
const QZ_DOWNLOAD_URL = "https://qz.io/download/";
const REPORT_URL_RE = /\/report\/(?:pdf|html|text)\//;
const FILE_PRINTER_RE = /print to file|save as pdf|save to pdf|microsoft print to pdf|cups-pdf/i;
const PRINTER_STORAGE_KEY = "narc_direct_print.printer";

let qzScriptPromise = null;
let qzSecurityReady = false;
let printEnv = null;

function isDirectPrintEnabled() {
    return session.narc_direct_print !== false;
}

function isOptedInReportName(reportName) {
    if (!reportName) {
        return false;
    }
    const names = session.narc_direct_print_reports || [];
    return names.includes(reportName);
}

function shouldDirectPrintAction(action) {
    if (!isDirectPrintEnabled() || !action) {
        return false;
    }
    if (action.report_print_behavior === "direct_print") {
        const reportType = action.report_type || "qweb-pdf";
        return ["qweb-pdf", "qweb-html", "qweb-text"].includes(reportType);
    }
    if (action.report_print_behavior) {
        return false;
    }
    return isOptedInReportName(action.report_name);
}

function getDocIds(action) {
    const ctx = action.context || {};
    if (Array.isArray(ctx.active_ids) && ctx.active_ids.length) {
        return ctx.active_ids;
    }
    if (ctx.active_id) {
        return [ctx.active_id];
    }
    return [];
}

function isReportPrintUrl(url) {
    if (!url || typeof url !== "string") {
        return false;
    }
    try {
        const parsed = new URL(url, browser.location.origin);
        return (
            REPORT_URL_RE.test(parsed.pathname) || parsed.pathname.includes("/report/download")
        );
    } catch {
        return REPORT_URL_RE.test(url) || url.includes("/report/download");
    }
}

function parseReportUrl(url) {
    if (!url || typeof url !== "string") {
        return null;
    }
    const parsed = new URL(url, browser.location.origin);
    const match = parsed.pathname.match(/\/report\/(?:pdf|html|text)\/([^/]+)(?:\/([^/]+))?/);
    if (!match) {
        return null;
    }
    const reportName = match[1];
    const ids = match[2]
        ? match[2]
              .split(",")
              .map((value) => Number.parseInt(value, 10))
              .filter((value) => Number.isInteger(value))
        : [];
    let data = {};
    let context = {};
    try {
        if (parsed.searchParams.get("options")) {
            data = JSON.parse(parsed.searchParams.get("options"));
        }
        if (parsed.searchParams.get("context")) {
            context = JSON.parse(parsed.searchParams.get("context"));
        }
    } catch {
        /* keep empty */
    }
    if (ids.length && !context.active_ids) {
        context.active_ids = ids;
    }
    return { report_name: reportName, data, context };
}

function base64ToBlob(base64, type) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type });
}

function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || "");
            resolve(result.split(",")[1] || "");
        };
        reader.onerror = () => reject(new Error("The report PDF could not be read."));
        reader.readAsDataURL(blob);
    });
}

function loadQzLibrary() {
    if (window.qz) {
        return Promise.resolve(window.qz);
    }
    if (qzScriptPromise) {
        return qzScriptPromise;
    }
    qzScriptPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = QZ_SCRIPT_URL;
        script.async = true;
        script.onload = () => {
            if (window.qz) {
                resolve(window.qz);
            } else {
                qzScriptPromise = null;
                reject(new Error("QZ Tray library loaded without a qz object."));
            }
        };
        script.onerror = () => {
            qzScriptPromise = null;
            reject(new Error("Could not load the QZ Tray library."));
        };
        document.head.appendChild(script);
    });
    return qzScriptPromise;
}

function setupQzSecurity(qz) {
    if (qzSecurityReady) {
        return;
    }
    qz.security.setCertificatePromise((resolve, reject) => {
        fetch("/narc_direct_print/qz/certificate", { credentials: "same-origin", cache: "no-store" })
            .then((response) => {
                if (!response.ok) {
                    throw new Error("The QZ certificate could not be loaded.");
                }
                return response.text();
            })
            .then(resolve)
            .catch(reject);
    });
    if (typeof qz.security.setSignatureAlgorithm === "function") {
        qz.security.setSignatureAlgorithm("SHA512");
    }
    qz.security.setSignaturePromise((toSign) => (resolve, reject) => {
        rpc("/narc_direct_print/qz/sign", { to_sign: toSign })
            .then(resolve)
            .catch(reject);
    });
    qzSecurityReady = true;
}

function printerNames(printers) {
    if (!printers) {
        return [];
    }
    return (Array.isArray(printers) ? printers : [printers]).filter(Boolean);
}

function normalizePrinterName(name) {
    return String(name || "")
        .toLowerCase()
        .replace(/[\s_\-]+/g, "");
}

function matchInstalledPrinter(wanted, installed) {
    if (!wanted) {
        return "";
    }
    const exact = installed.find((name) => name === wanted);
    if (exact) {
        return exact;
    }
    const needle = normalizePrinterName(wanted);
    if (!needle) {
        return "";
    }
    return (
        installed.find((name) => normalizePrinterName(name) === needle) ||
        installed.find((name) => {
            const hay = normalizePrinterName(name);
            return hay.includes(needle) || needle.includes(hay);
        }) ||
        ""
    );
}

async function resolveDefaultPrinter(qz) {
    const found = printerNames(await qz.printers.find());
    const real = found.filter((name) => !FILE_PRINTER_RE.test(name));
    const preferred = String(session.narc_direct_print_printer || "").trim();
    const fromSettings = matchInstalledPrinter(preferred, real);
    if (fromSettings) {
        return fromSettings;
    }

    const stored = String(browser.localStorage.getItem(PRINTER_STORAGE_KEY) || "").trim();
    const fromStored = matchInstalledPrinter(stored, real);
    if (fromStored) {
        return fromStored;
    }

    const osDefault = await qz.printers.getDefault();
    if (osDefault && !FILE_PRINTER_RE.test(osDefault)) {
        return matchInstalledPrinter(osDefault, real) || osDefault;
    }
    if (real.length) {
        return real[0];
    }
    throw new Error(_t("Set a default printer on this computer, then click Print again."));
}

function withTimeout(promise, timeoutMs, message) {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), timeoutMs);
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function abortQzConnect(qz) {
    try {
        const result = qz?.websocket?.disconnect?.();
        if (result && typeof result.catch === "function") {
            result.catch(() => {});
        }
    } catch {
        /* a hung localhost websocket must not block the UI */
    }
}

async function connectQz(qz, { retries = 0, timeoutMs = 1000, probe = false } = {}) {
    if (qz.websocket.isActive()) {
        return;
    }
    const options = probe
        ? {
              retries: 0,
              delay: 0,
              host: ["localhost"],
              usingSecure: true,
              port: { secure: [8181], insecure: [] },
          }
        : {
              retries,
              delay: 0,
              host: ["localhost", "localhost.qz.io"],
          };
    const connectPromise = qz.websocket.connect(options);
    connectPromise.catch(() => {});
    try {
        await withTimeout(connectPromise, timeoutMs, "QZ Tray is not running.");
        if (!qz.websocket.isActive()) {
            throw new Error("QZ Tray is not running.");
        }
    } catch (error) {
        abortQzConnect(qz);
        throw error instanceof Error ? error : new Error("QZ Tray is not running.");
    }
}

async function qzIsReady() {
    try {
        const qz = await loadQzLibrary();
        setupQzSecurity(qz);
        await connectQz(qz, { probe: true, timeoutMs: 800 });
        await withTimeout(qz.printers.getDefault(), 800, "QZ Tray is not running.");
        return true;
    } catch {
        abortQzConnect(window.qz);
        return false;
    }
}

function isQzMissingError(error) {
    const message = String(error?.message || error || "").toLowerCase();
    return (
        message.includes("qz tray is not running") ||
        message.includes("unable to establish connection") ||
        message.includes("connection attempt") ||
        message.includes("websocket") ||
        message.includes("not running")
    );
}

async function printWithQz(base64, jobName) {
    const qz = await loadQzLibrary();
    setupQzSecurity(qz);
    await connectQz(qz, { retries: 0, timeoutMs: 2000 });
    const printer = await withTimeout(
        resolveDefaultPrinter(qz),
        3000,
        _t("Could not reach QZ Tray or the default printer.")
    );
    const config = qz.configs.create(printer, {
        copies: 1,
        jobName: jobName || "Odoo Report",
        rasterize: true,
    });
    await qz.print(config, [
        {
            type: "pixel",
            format: "pdf",
            flavor: "base64",
            data: base64,
        },
    ]);
    browser.localStorage.setItem(PRINTER_STORAGE_KEY, printer);
    return printer;
}

function isWindowsPc() {
    const platform = navigator.userAgentData?.platform || navigator.platform || "";
    return /win/i.test(platform) || /windows/i.test(navigator.userAgent || "");
}

function pcSetupUrl() {
    return isWindowsPc() ? "/narc_direct_print/qz/setup.bat" : "/narc_direct_print/qz/setup.sh";
}

function startPcSetup() {
    const link = document.createElement("a");
    link.href = pcSetupUrl();
    link.setAttribute("download", isWindowsPc() ? "narc-print-setup.bat" : "narc-print-setup.sh");
    link.rel = "noopener noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
}

function offerAutoSetup(env, error) {
    const detail = error?.message ? String(error.message) : "";
    startPcSetup();
    if (env.services.dialog) {
        env.services.dialog.add(ConfirmationDialog, {
            title: _t("Set up this computer for printing"),
            body: _t(
                "The setup file is downloading now. Open it and allow administrator permission once. If Windows blocks it, choose More info, then Run anyway. If QZ Tray cannot be downloaded, the QZ website will open — install it, then run the setup file again. After that, Print PDF goes to the default printer."
            ),
            confirmLabel: _t("Download setup again"),
            cancelLabel: _t("Close"),
            confirm: () => startPcSetup(),
        });
        return;
    }
    env.services.notification.add(
        _t(
            "This computer is not set up for direct print yet.%s",
            detail ? ` (${detail})` : ""
        ),
        {
            title: _t("Set up this computer"),
            type: "danger",
            sticky: true,
            buttons: [
                {
                    name: _t("Set up this computer"),
                    primary: true,
                    onClick: () => startPcSetup(),
                },
                {
                    name: _t("Download QZ Tray"),
                    onClick: () => browser.open(QZ_DOWNLOAD_URL, "_blank", "noopener,noreferrer"),
                },
            ],
        }
    );
}

function printPdfBlob(base64) {
    return new Promise((resolve, reject) => {
        const blob = base64ToBlob(base64, "application/pdf");
        const pdfUrl = URL.createObjectURL(blob);
        const iframe = document.createElement("iframe");
        iframe.setAttribute("aria-hidden", "true");
        Object.assign(iframe.style, {
            position: "fixed",
            width: "0",
            height: "0",
            border: "0",
            left: "0",
            top: "0",
        });

        let settled = false;
        const cleanup = () => {
            setTimeout(() => {
                iframe.remove();
                URL.revokeObjectURL(pdfUrl);
            }, 60000);
        };
        const succeed = () => {
            if (settled) {
                return;
            }
            settled = true;
            cleanup();
            resolve();
        };
        const fail = (error) => {
            if (settled) {
                return;
            }
            settled = true;
            cleanup();
            reject(error);
        };
        const triggerPrint = () => {
            const frameWindow = iframe.contentWindow;
            if (!frameWindow) {
                fail(new Error("Print frame is not available."));
                return;
            }
            try {
                frameWindow.focus();
                frameWindow.print();
                succeed();
            } catch (error) {
                fail(error);
            }
        };

        iframe.srcdoc = `<!DOCTYPE html>
<html>
  <head><meta charset="utf-8"/></head>
  <body style="margin:0">
    <embed type="application/pdf" src="${pdfUrl}" width="100%" height="100%"/>
  </body>
</html>`;
        iframe.onload = () => setTimeout(triggerPrint, 350);
        iframe.onerror = () => fail(new Error("The report PDF could not be loaded."));
        document.body.appendChild(iframe);
        setTimeout(() => {
            if (!settled) {
                triggerPrint();
            }
        }, 1800);
    });
}

function printTextContent(text) {
    return new Promise((resolve, reject) => {
        const iframe = document.createElement("iframe");
        iframe.setAttribute("aria-hidden", "true");
        Object.assign(iframe.style, {
            position: "fixed",
            width: "0",
            height: "0",
            border: "0",
        });
        iframe.srcdoc = `<!DOCTYPE html>
<html>
  <body style="margin:0">
    <pre style="font:12px/1.4 monospace;white-space:pre-wrap">${String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")}</pre>
  </body>
</html>`;
        iframe.onload = () => {
            try {
                iframe.contentWindow.focus();
                iframe.contentWindow.print();
                resolve();
            } catch (error) {
                reject(error);
            } finally {
                setTimeout(() => iframe.remove(), 60000);
            }
        };
        document.body.appendChild(iframe);
    });
}

async function sendPayloadToPrinter(payload, env) {
    if (payload?.text) {
        await printTextContent(payload.text);
        return;
    }
    if (!payload?.pdf_base64) {
        throw new Error(_t("The report PDF could not be generated."));
    }
    try {
        const printer = await printWithQz(payload.pdf_base64, payload.name);
        env.services.notification.add(_t("Sent to printer: %s", printer), { type: "success" });
    } catch (error) {
        if (isQzMissingError(error)) {
            offerAutoSetup(env, error);
            return;
        }
        env.services.notification.add(
            error?.message || _t("Could not print the report."),
            { type: "danger", sticky: true }
        );
    }
}

async function printReport(action, env) {
    const ready = await qzIsReady();
    if (!ready) {
        offerAutoSetup(env, new Error(_t("QZ Tray is not running on this computer.")));
        return;
    }
    env.services.ui.block();
    try {
        const result = await rpc("/report/direct_print/pdf", {
            report_name: action.report_name,
            docids: getDocIds(action),
            data: action.data || {},
            context: action.context || {},
        });
        env.services.ui.unblock();
        await sendPayloadToPrinter(result, env);
    } catch (error) {
        if (env.services.ui.isBlocked) {
            env.services.ui.unblock();
        }
        env.services.notification.add(
            error?.data?.message || error?.message || _t("Could not print the report."),
            { type: "danger", sticky: true }
        );
    }
}

async function printFromUrl(url, env) {
    const parsed = parseReportUrl(url);
    if (!parsed || !isOptedInReportName(parsed.report_name)) {
        return false;
    }
    await printReport(parsed, env);
    return true;
}

async function narcDirectPrintHandler(action, _options, env) {
    if (!shouldDirectPrintAction(action)) {
        return false;
    }
    await printReport(action, env);
    return true;
}

registry
    .category("ir.actions.report handlers")
    .add("narc_direct_print_handler", narcDirectPrintHandler, { sequence: 1 });

patch(ReportAction.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
    },

    async print() {
        if (!isDirectPrintEnabled()) {
            return super.print(...arguments);
        }
        let behavior = this.props.report_print_behavior;
        if (!behavior && this.props.report_name) {
            const reports = await this.orm.searchRead(
                "ir.actions.report",
                [["report_name", "=", this.props.report_name]],
                ["report_print_behavior"],
                { limit: 1 }
            );
            behavior = reports[0]?.report_print_behavior;
        }
        if (behavior !== "direct_print") {
            return super.print(...arguments);
        }
        await printReport(
            {
                report_name: this.props.report_name,
                data: this.props.data || {},
                context: this.props.context || {},
            },
            this.env
        );
    },
});

patch(actionService, {
    start(env) {
        printEnv = env;
        if (isDirectPrintEnabled()) {
            loadQzLibrary().catch(() => {});
        }
        const services = super.start(...arguments);
        const originalDoAction = services.doAction;
        services.doAction = async function (actionRequest, options = {}) {
            if (
                isDirectPrintEnabled() &&
                actionRequest &&
                typeof actionRequest === "object" &&
                actionRequest.type === "ir.actions.act_url" &&
                isReportPrintUrl(actionRequest.url)
            ) {
                const handled = await printFromUrl(actionRequest.url, env);
                if (handled) {
                    if (actionRequest.close) {
                        return originalDoAction.call(
                            this,
                            { type: "ir.actions.act_window_close" },
                            options
                        );
                    }
                    options.onClose?.();
                    return true;
                }
            }
            return originalDoAction.call(this, actionRequest, options);
        };
        return services;
    },
});

const originalOpen = browser.open.bind(browser);
browser.open = (url, target, features) => {
    if (isDirectPrintEnabled() && isReportPrintUrl(url) && printEnv) {
        const parsed = parseReportUrl(url);
        if (parsed && isOptedInReportName(parsed.report_name)) {
            printFromUrl(url, printEnv);
            return null;
        }
    }
    return originalOpen(url, target, features);
};
