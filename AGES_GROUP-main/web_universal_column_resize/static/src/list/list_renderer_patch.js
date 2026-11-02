/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { usePersistentColumnWidths } from "./persistent_column_width_hook";
import { hasSavedWidths } from "./width_store";

/**
 * Stable localStorage key for a list / x2many — does not include the full
 * field list so toggling optional columns does not orphan saved widths.
 */
function buildPersistentColumnWidthsKey(renderer) {
    const nested = renderer.props.nestedKeyOptionalFieldsData;
    if (nested?.model && nested?.field) {
        return `x2m,${nested.model},${nested.viewMode || "form"},${nested.field}`;
    }
    const model = renderer.props.list?.resModel || "unknown";
    const viewId = renderer.env?.config?.viewId || 0;
    return `list,${model},${viewId}`;
}

/**
 * Universal list column resize persistence.
 * Covers every ListRenderer usage: standard lists, sale/purchase order lines,
 * one2many / many2many embedded lists, etc.
 */
patch(ListRenderer.prototype, {
    setup() {
        const wantsMagic = this.constructor.useMagicColumnWidths;
        const ctor = this.constructor;
        const originalMagic = ctor.useMagicColumnWidths;
        ctor.useMagicColumnWidths = false;
        try {
            super.setup();
        } finally {
            ctor.useMagicColumnWidths = originalMagic;
        }
        if (wantsMagic) {
            this.columnWidths = usePersistentColumnWidths(
                this.tableRef,
                () => ({
                    columns: this.columns,
                    isEmpty:
                        !this.props.list.records.length ||
                        this.props.list.model.useSampleModel,
                    hasSelectors: this.hasSelectors,
                    hasOpenFormViewColumn: this.hasOpenFormViewColumn,
                    hasActionsColumn: this.hasActionsColumn,
                }),
                () => buildPersistentColumnWidthsKey(this)
            );
        }
    },

    get displayOptionalFields() {
        return super.displayOptionalFields || this.hasPersistedColumnWidths;
    },

    get persistentColumnWidthsKey() {
        return buildPersistentColumnWidthsKey(this);
    },
    get hasPersistedColumnWidths() {
        return !!(this.persistentColumnWidthsKey && hasSavedWidths(this.persistentColumnWidthsKey));
    },

    get resetColumnWidthsLabel() {
        return _t("Reset column widths");
    },

    onResetColumnWidths() {
        this.columnWidths?.resetView?.();
    },
});
