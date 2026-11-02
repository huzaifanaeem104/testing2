/** @odoo-module **/

import { Component, useState, useExternalListener } from "@odoo/owl";

export function optionalColumnDefaults(columns) {
    const result = {};
    for (const column of columns || []) {
        result[column.id] = Boolean(column.defaultVisible);
    }
    return result;
}

export class ReportOptionalColumns extends Component {
    static template = "ages_custom_reports.ReportOptionalColumns";
    static props = {
        columns: { type: Array },
        visible: { type: Object },
        onToggle: { type: Function },
    };

    setup() {
        this.state = useState({ open: false, top: 0, left: 0 });
        useExternalListener(window, "click", () => {
            this.state.open = false;
        });
        useExternalListener(window, "resize", () => {
            this.state.open = false;
        });
    }

    get hasActive() {
        return (this.props.columns || []).some((column) => {
            if (column.defaultVisible) {
                return false;
            }
            return this.isOn(column.id);
        });
    }

    get menuStyle() {
        return `top: ${this.state.top}px; left: ${this.state.left}px;`;
    }

    isOn(columnId) {
        return Boolean(this.props.visible?.[columnId]);
    }

    toggleMenu(ev) {
        ev.stopPropagation();
        const next = !this.state.open;
        this.state.open = next;
        if (!next) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        const width = 260;
        this.state.top = rect.bottom + 4;
        this.state.left = Math.max(8, rect.right - width);
    }

    onSwitch(ev, columnId) {
        ev.stopPropagation();
        this.props.onToggle(columnId);
    }
}

export const ReportOptionalColumnMixin = {
    isColumnVisible(columnId) {
        const cols = this.state.optionalColumns || {};
        if (Object.prototype.hasOwnProperty.call(cols, columnId)) {
            return Boolean(cols[columnId]);
        }
        const def = (this.optionalColumnDefs || []).find((column) => column.id === columnId);
        return Boolean(def?.defaultVisible);
    },

    toggleOptionalColumn(columnId) {
        if (typeof this.onOptionalColumnToggle === "function") {
            if (this.onOptionalColumnToggle(columnId)) {
                return;
            }
        }
        const next = { ...(this.state.optionalColumns || {}) };
        next[columnId] = !this.isColumnVisible(columnId);
        this.state.optionalColumns = next;
        this._reportPersistence?.persistFilters(this.state);
    },
};

export function applyReportOptionalColumns(ctor) {
    const descriptors = Object.getOwnPropertyDescriptors(ReportOptionalColumnMixin);
    delete descriptors.constructor;
    Object.defineProperties(ctor.prototype, descriptors);
}
