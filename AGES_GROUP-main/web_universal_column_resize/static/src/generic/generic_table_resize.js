/** @odoo-module **/

import { localization } from "@web/core/l10n/localization";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

const STORAGE_PREFIX = "web_universal_column_resize.generic.v3.";
const MIN_WIDTH = 48;

const frozenWidths = new WeakMap();
const resizingTables = new WeakSet();

/**
 * Leaf columns only: last header row, plus rowspan cells from earlier rows.
 * Never treat colspan title cells ("As of …") as columns.
 */
function getLeafHeaders(table) {
    const rows = [...table.querySelectorAll(":scope > thead > tr")];
    if (!rows.length) {
        return [];
    }
    const lastRow = rows[rows.length - 1];
    const lastCells = [...lastRow.children].filter((el) => el.tagName === "TH");
    const lastHasColspan = lastCells.some((th) => Number(th.colSpan || 1) > 1);
    if (lastHasColspan) {
        return lastCells.filter((th) => Number(th.colSpan || 1) === 1);
    }
    const rowspanCells = [];
    if (rows.length > 1) {
        for (const th of rows[0].children) {
            if (th.tagName !== "TH") {
                continue;
            }
            if (Number(th.rowSpan || 1) > 1 && Number(th.colSpan || 1) === 1) {
                rowspanCells.push(th);
            }
        }
    }
    return [...rowspanCells, ...lastCells];
}

function tableStorageKey(table) {
    const reportClass =
        [...table.classList].find((c) => /^o_ages_\w+_table$/.test(c)) ||
        table.closest("[class*='o_ages_']")?.className.match(/o_ages_\w+_report/)?.[0] ||
        [...table.classList].filter((c) => c !== "table" && !c.startsWith("o_")).join(".") ||
        "table";
    const headers = getLeafHeaders(table).map((th, index) => {
        const colClass = [...th.classList].find(
            (c) => c.startsWith("o_ages_") || c.includes("_col") || c.startsWith("o_column")
        );
        if (colClass) {
            return colClass;
        }
        const clone = th.cloneNode(true);
        clone.querySelectorAll(".o_universal_resize, .o_resize, button").forEach((el) => el.remove());
        const label = (clone.textContent || "").replace(/\s+/g, " ").trim().slice(0, 32);
        return label || `th${index}`;
    });
    return STORAGE_PREFIX + reportClass + "::" + headers.join("|");
}

function load(table) {
    try {
        const raw = browser.localStorage.getItem(tableStorageKey(table));
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw);
        if (parsed && parsed.v === 3 && Array.isArray(parsed.widths)) {
            return parsed.widths.filter((n) => typeof n === "number" && n > 0);
        }
        return null;
    } catch {
        return null;
    }
}

function save(table, widths) {
    try {
        browser.localStorage.setItem(
            tableStorageKey(table),
            JSON.stringify({ v: 3, widths: widths.map((w) => Math.round(w)) })
        );
    } catch {
        // ignore
    }
}

function ensureColgroup(table, count) {
    let colgroup = table.querySelector(":scope > colgroup.o_universal_colgroup");
    if (!colgroup) {
        colgroup = document.createElement("colgroup");
        colgroup.className = "o_universal_colgroup";
        table.insertBefore(colgroup, table.firstChild);
    }
    while (colgroup.children.length < count) {
        colgroup.appendChild(document.createElement("col"));
    }
    while (colgroup.children.length > count) {
        colgroup.lastChild.remove();
    }
    return colgroup;
}

function applyWidths(table, headers, widths) {
    if (!headers.length || widths.length !== headers.length) {
        return;
    }
    const colgroup = ensureColgroup(table, headers.length);
    let total = 0;
    headers.forEach((th, index) => {
        const px = Math.max(MIN_WIDTH, Math.round(widths[index]));
        const col = colgroup.children[index];
        col.style.width = `${px}px`;
        th.style.width = `${px}px`;
        th.style.minWidth = `${px}px`;
        th.style.maxWidth = `${px}px`;
        total += px;
    });
    table.style.tableLayout = "fixed";
    table.style.width = `${total}px`;
    table.style.minWidth = `${total}px`;
    table.style.maxWidth = "none";
    frozenWidths.set(table, widths.map((w) => Math.max(MIN_WIDTH, Math.round(w))));
}

function measureNaturalWidths(table, headers) {
    const colgroup = table.querySelector(":scope > colgroup.o_universal_colgroup");
    const prevLayout = table.style.tableLayout;
    const prevWidth = table.style.width;
    const prevMin = table.style.minWidth;
    const prevMax = table.style.maxWidth;
    colgroup?.remove();
    table.style.tableLayout = "auto";
    table.style.width = "auto";
    table.style.minWidth = "";
    table.style.maxWidth = "";
    headers.forEach((th) => {
        th.style.width = "";
        th.style.minWidth = "";
        th.style.maxWidth = "";
    });
    const widths = headers.map((th) =>
        Math.max(MIN_WIDTH, Math.round(th.getBoundingClientRect().width))
    );
    table.style.tableLayout = prevLayout;
    table.style.width = prevWidth;
    table.style.minWidth = prevMin;
    table.style.maxWidth = prevMax;
    return widths;
}

function freezeTableColumns(table) {
    const headers = getLeafHeaders(table);
    if (!headers.length) {
        return headers;
    }
    const saved = load(table);
    if (saved && saved.length === headers.length) {
        applyWidths(table, headers, saved);
        return headers;
    }
    const current = frozenWidths.get(table);
    const currentLooksReal = current && current.some((width) => width > MIN_WIDTH + 8);
    if (currentLooksReal && current.length === headers.length) {
        applyWidths(table, headers, current);
        return headers;
    }
    const measured = measureNaturalWidths(table, headers);
    if (!currentLooksReal || measured.some((width) => width > MIN_WIDTH + 8)) {
        applyWidths(table, headers, measured);
    }
    return headers;
}

function addHandle(table, th) {
    if (th.querySelector(":scope > .o_universal_resize")) {
        return;
    }
    if (Number(th.colSpan || 1) > 1) {
        return;
    }
    th.classList.add("position-relative");
    const handle = document.createElement("span");
    handle.className = "o_universal_resize";
    handle.title = "Drag to resize column";
    handle.addEventListener("pointerdown", (ev) => startResize(ev, table, th));
    th.appendChild(handle);
}

function ensureHandles(table) {
    if (!(table instanceof HTMLTableElement)) {
        return;
    }
    if (table.classList.contains("o_list_table") || table.closest(".o_list_renderer")) {
        return;
    }
    if (resizingTables.has(table)) {
        return;
    }
    const headers = getLeafHeaders(table);
    if (!headers.length) {
        return;
    }
    table.classList.add("o_universal_resizable_table");
    freezeTableColumns(table);
    headers.forEach((th) => addHandle(table, th));
    table.dataset.universalResize = "1";
}

function startResize(ev, table, th) {
    ev.preventDefault();
    ev.stopPropagation();
    if (typeof ev.target.setPointerCapture === "function" && ev.pointerId != null) {
        try {
            ev.target.setPointerCapture(ev.pointerId);
        } catch {
            // ignore
        }
    }

    const headers = freezeTableColumns(table);
    const index = headers.indexOf(th);
    if (index < 0) {
        return;
    }

    const startWidths = (frozenWidths.get(table) || headers.map((header) =>
        Math.round(header.getBoundingClientRect().width)
    )).slice();
    const initialX = ev.clientX;
    const initialWidth = startWidths[index];

    resizingTables.add(table);
    table.classList.add("o_resizing");
    th.classList.add("o_column_resizing");

    const onMove = (moveEv) => {
        let delta = moveEv.clientX - initialX;
        delta = localization.direction === "rtl" ? -delta : delta;
        const next = startWidths.slice();
        next[index] = Math.max(MIN_WIDTH, initialWidth + delta);
        applyWidths(table, headers, next);
    };

    const onStop = () => {
        table.classList.remove("o_resizing");
        th.classList.remove("o_column_resizing");
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onStop);
        const widths = frozenWidths.get(table);
        if (widths) {
            save(table, widths);
        }
        resizingTables.delete(table);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onStop);
}

function scan(root = document) {
    const scope = root instanceof HTMLElement || root === document ? root : document;
    const selector = [
        ".o_ages_bs_report table",
        ".o_ages_gl_report table",
        ".o_ages_pl_report table",
        ".o_ages_ja_report table",
        ".o_ages_es_report table",
        ".o_ages_cf_report table",
        ".o_ages_pdl_report table",
        ".o_ages_tr_report table",
        ".o_ages_tb_report table",
        ".o_ages_bs_content table",
        ".account_report table.table",
        ".o_content table.o_ages_gl_table",
        ".o_content table.o_ages_pl_table",
        ".o_content table.o_ages_bs_table",
    ].join(", ");

    if (scope instanceof HTMLTableElement) {
        ensureHandles(scope);
    }
    scope.querySelectorAll?.(selector).forEach(ensureHandles);
}

export const universalTableResizeService = {
    dependencies: [],
    start() {
        scan();
        const observer = new MutationObserver((mutations) => {
            let needsScan = false;
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node instanceof HTMLElement) {
                        needsScan = true;
                        break;
                    }
                }
                if (mutation.type === "childList" && mutation.target instanceof HTMLElement) {
                    const table =
                        mutation.target.closest?.("table") ||
                        (mutation.target instanceof HTMLTableElement ? mutation.target : null);
                    if (
                        table instanceof HTMLTableElement &&
                        table.dataset.universalResize === "1" &&
                        !resizingTables.has(table)
                    ) {
                        freezeTableColumns(table);
                    }
                }
            }
            if (needsScan) {
                scan();
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
        browser.setTimeout(() => scan(), 0);
        browser.setTimeout(() => scan(), 300);
        return {
            rescan: () => scan(),
        };
    },
};

registry.category("services").add("web_universal_column_resize.generic", universalTableResizeService);
