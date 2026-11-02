/** @odoo-module **/

import { onMounted, onWillUnmount } from "@odoo/owl";

export const LEDGER_ROW_HEIGHT = 34;
export const LEDGER_ROW_BUFFER = 18;
export const LEDGER_VIRTUALIZE_AFTER = 80;

export function ledgerWindow(lines, scrollTop, viewportHeight) {
    const total = lines.length;
    if (total <= LEDGER_VIRTUALIZE_AFTER) {
        return { lines, top: 0, bottom: 0 };
    }
    const start = Math.max(0, Math.floor((scrollTop || 0) / LEDGER_ROW_HEIGHT) - LEDGER_ROW_BUFFER);
    const count = Math.ceil((viewportHeight || 640) / LEDGER_ROW_HEIGHT) + LEDGER_ROW_BUFFER * 2;
    const end = Math.min(total, start + count);
    return {
        lines: lines.slice(start, end),
        top: start * LEDGER_ROW_HEIGHT,
        bottom: Math.max(0, (total - end) * LEDGER_ROW_HEIGHT),
    };
}

export function setupLedgerVirtualScroll(component) {
    const measure = () => {
        const scroller = component._ledgerScroller;
        if (scroller) {
            component.state.viewportHeight = scroller.clientHeight || 640;
        }
    };
    const onScroll = () => {
        const scroller = component._ledgerScroller;
        if (scroller) {
            component.state.scrollTop = scroller.scrollTop;
        }
    };
    component._measureLedgerViewport = measure;
    component.onLedgerScroll = onScroll;
    onMounted(() => {
        const root = component.rootRef?.el;
        let scroller = root?.querySelector(".o_content");
        if (!scroller) {
            let node = root;
            while (node && node !== document.body) {
                const style = window.getComputedStyle(node);
                if (style.overflowY === "auto" || style.overflowY === "scroll") {
                    scroller = node;
                    break;
                }
                node = node.parentElement;
            }
        }
        component._ledgerScroller = scroller || root;
        if (component._ledgerScroller) {
            component._ledgerScroller.addEventListener("scroll", onScroll, { passive: true });
        }
        measure();
        window.addEventListener("resize", measure);
    });
    onWillUnmount(() => {
        if (component._ledgerScroller) {
            component._ledgerScroller.removeEventListener("scroll", onScroll);
        }
        window.removeEventListener("resize", measure);
    });
}
