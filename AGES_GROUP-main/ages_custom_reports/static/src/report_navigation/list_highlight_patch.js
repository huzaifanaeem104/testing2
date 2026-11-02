/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

const HIGHLIGHT_STORAGE_KEY = "ages_highlight_move_line_id";
const TAB_DONE_KEY = "ages_highlight_aml_tab_done";

function storedHighlightMoveLineId() {
    try {
        return Number(sessionStorage.getItem(HIGHLIGHT_STORAGE_KEY) || false) || false;
    } catch (_err) {
        return false;
    }
}

function isAccountMoveFormList(renderer) {
    const form = renderer.tableRef?.el?.closest(".o_form_view");
    if (!form) {
        return false;
    }
    return Boolean(
        form.querySelector(
            ".o_field_widget[name='invoice_line_ids'], .o_field_widget[name='line_ids']"
        )
    );
}

function highlightMoveLineId(renderer) {
    if (renderer.props.list?.resModel !== "account.move.line") {
        return false;
    }
    const sources = [
        renderer.env.searchModel?.context,
        renderer.env.config?.context,
        renderer.props.list?.model?.config?.context,
        renderer.props.list?.model?.root?.context,
        renderer.props.list?.context,
    ];
    for (const source of sources) {
        const id = Number(source?.ages_highlight_move_line_id || false);
        if (id) {
            return id;
        }
    }
    // Do not reuse a leftover report highlight on a normal invoice form.
    // That kept clicking the Journal Items tab whenever Invoice Lines mounted.
    if (isAccountMoveFormList(renderer)) {
        return false;
    }
    return storedHighlightMoveLineId();
}

function activateJournalItemsTab(renderer) {
    const lineId = highlightMoveLineId(renderer);
    if (!lineId) {
        return;
    }
    try {
        if (sessionStorage.getItem(TAB_DONE_KEY) === String(lineId)) {
            return;
        }
        sessionStorage.setItem(TAB_DONE_KEY, String(lineId));
    } catch (_err) {
        if (renderer._agesJournalTabRequested) {
            return;
        }
        renderer._agesJournalTabRequested = true;
    }
    const form = renderer.tableRef?.el?.closest(".o_form_view");
    if (!form) {
        return;
    }
    const links = form.querySelectorAll(".o_notebook .nav-link");
    for (const link of links) {
        if ((link.textContent || "").trim() !== "Journal Items") {
            continue;
        }
        if (!link.classList.contains("active")) {
            link.click();
        }
        return;
    }
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        this._agesScrolledHighlightId = false;
        onMounted(() => this._agesScrollToHighlightedLine());
        onPatched(() => this._agesScrollToHighlightedLine());
    },

    getRowClass(record) {
        const classNames = super.getRowClass(record);
        const lineId = highlightMoveLineId(this);
        if (lineId && record.resId === lineId) {
            return `${classNames} o_ages_highlight_aml`.trim();
        }
        return classNames;
    },

    _agesScrollToHighlightedLine() {
        const lineId = highlightMoveLineId(this);
        if (!lineId || this._agesScrolledHighlightId === lineId) {
            return;
        }
        const row = this.tableRef?.el?.querySelector("tr.o_ages_highlight_aml");
        if (!row) {
            activateJournalItemsTab(this);
            return;
        }
        this._agesScrolledHighlightId = lineId;
        row.scrollIntoView({ block: "center", behavior: "smooth" });
    },
});
