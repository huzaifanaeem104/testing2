import { reactive } from "@odoo/owl";

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

const WIDTH_KEY = "ages_chatter_width";
const HIDDEN_KEY = "ages_chatter_hidden";
const DEFAULT_WIDTH = 530;
const MIN_WIDTH = 280;

function readWidth() {
    const raw = parseInt(browser.localStorage.getItem(WIDTH_KEY) || "", 10);
    if (Number.isNaN(raw)) {
        return DEFAULT_WIDTH;
    }
    return Math.max(MIN_WIDTH, raw);
}

export const agesChatterResizeService = {
    start() {
        const state = reactive({
            hidden: browser.localStorage.getItem(HIDDEN_KEY) === "1",
            width: readWidth(),
            defaultWidth: DEFAULT_WIDTH,
            minWidth: MIN_WIDTH,
            setHidden(hidden) {
                state.hidden = Boolean(hidden);
                browser.localStorage.setItem(HIDDEN_KEY, state.hidden ? "1" : "0");
            },
            setWidth(width) {
                const next = Math.max(MIN_WIDTH, Math.round(width));
                state.width = next;
                browser.localStorage.setItem(WIDTH_KEY, String(next));
            },
            resetWidth() {
                state.setWidth(DEFAULT_WIDTH);
            },
        });
        return state;
    },
};

registry.category("services").add("ages.chatter_resize", agesChatterResizeService);
