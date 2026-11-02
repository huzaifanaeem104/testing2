/** @odoo-module **/

import { browser } from "@web/core/browser/browser";

const PREFIX = "web_universal_column_resize.";

/**
 * @param {string} key
 * @returns {Record<string, number>|null} map of columnId -> content width (px)
 */
export function loadWidthMap(key) {
    if (!key) {
        return null;
    }
    try {
        const raw = browser.localStorage.getItem(PREFIX + key);
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw);
        // v2: { v: 2, cols: { id: width, ... } }
        if (parsed && parsed.v === 2 && parsed.cols && typeof parsed.cols === "object") {
            const cols = {};
            for (const [id, width] of Object.entries(parsed.cols)) {
                if (typeof width === "number" && width > 0) {
                    cols[id] = width;
                }
            }
            return Object.keys(cols).length ? cols : null;
        }
        // Legacy: number[] — cannot map to ids; ignore (user re-saves on next resize)
        return null;
    } catch {
        return null;
    }
}

/**
 * Resolve stored widths into an array aligned with current header column ids.
 * Returns null if fewer than half of the data columns are present (treat as missing).
 *
 * @param {string} key
 * @param {string[]} headerIds
 * @returns {number[]|null}
 */
export function resolveWidths(key, headerIds) {
    const map = loadWidthMap(key);
    if (!map || !headerIds?.length) {
        return null;
    }
    const dataIds = headerIds.filter((id) => !String(id).startsWith("__"));
    const hit = dataIds.filter((id) => typeof map[id] === "number").length;
    if (dataIds.length && hit < Math.ceil(dataIds.length / 2)) {
        return null;
    }
    return headerIds.map((id, index) => {
        if (typeof map[id] === "number") {
            return map[id];
        }
        // Fallback for chrome columns (selector / actions)
        if (id === "__selector__") {
            return 20;
        }
        if (id === "__open_form__") {
            return 54;
        }
        if (id === "__actions__") {
            return 12;
        }
        // Unknown / new optional column: leave a sensible min; caller may still freeze
        return map[headerIds[index]] || 80;
    });
}

/**
 * @param {string} key
 * @param {string[]} headerIds
 * @param {number[]} widths
 */
export function saveWidths(key, headerIds, widths) {
    if (!key || !headerIds?.length || !widths?.length || headerIds.length !== widths.length) {
        return;
    }
    try {
        const cols = {};
        headerIds.forEach((id, index) => {
            const w = widths[index];
            if (typeof w === "number" && w > 0) {
                cols[id] = Math.round(w);
            }
        });
        browser.localStorage.setItem(PREFIX + key, JSON.stringify({ v: 2, cols }));
    } catch {
        // Quota / private mode — ignore.
    }
}

/**
 * Legacy helper used by optional-columns menu visibility.
 * @param {string} key
 * @returns {boolean}
 */
export function hasSavedWidths(key) {
    return !!loadWidthMap(key);
}

/**
 * @param {string} key
 */
export function clearWidths(key) {
    if (!key) {
        return;
    }
    try {
        browser.localStorage.removeItem(PREFIX + key);
    } catch {
        // ignore
    }
}

/** @deprecated use resolveWidths */
export function loadWidths(key) {
    return loadWidthMap(key) ? Object.values(loadWidthMap(key)) : null;
}
