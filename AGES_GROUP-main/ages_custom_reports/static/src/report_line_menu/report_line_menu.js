/** @odoo-module **/

import { Component, useState, useExternalListener, useRef } from "@odoo/owl";

export class ReportLineMenu extends Component {
    static template = "ages_custom_reports.ReportLineMenu";
    static props = {
        items: { type: Array },
    };

    setup() {
        this.state = useState({ open: false, top: 0, left: 0 });
        this.menuRef = useRef("menu");
        this.btnRef = useRef("menuBtn");

        this._onWindowClick = () => {
            this.state.open = false;
        };
        useExternalListener(window, "click", this._onWindowClick);
    }

    _positionDropdown() {
        const btn = this.btnRef.el;
        if (!btn) {
            return;
        }
        const rect = btn.getBoundingClientRect();
        this.state.top = rect.bottom + 2;
        this.state.left = rect.right;
    }

    toggleMenu(ev) {
        ev.stopPropagation();
        const next = !this.state.open;
        this.state.open = next;
        if (next) {
            this._positionDropdown();
        }
    }

    onItemClick(ev, item) {
        ev.stopPropagation();
        this.state.open = false;
        if (item.onClick) {
            item.onClick();
        }
    }

    get dropdownStyle() {
        return `top: ${this.state.top}px; left: ${this.state.left}px;`;
    }
}
