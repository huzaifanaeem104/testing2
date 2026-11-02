/** @odoo-module **/

import { Component, useState, useRef, onWillStart, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const SCREEN_META = {
    today: { method: "get_today", title: "Today" },
    contracts: { method: "get_contracts", title: "Contracts" },
    site: { method: "get_site", title: "Site" },
    spend: { method: "get_spend", title: "Spend" },
    books: { method: "get_books", title: "Books" },
};

export const WORKS_SCREENS = [
    { key: "today", title: "Today" },
    { key: "contracts", title: "Contracts" },
    { key: "site", title: "Site" },
    { key: "spend", title: "Spend" },
    { key: "books", title: "Books" },
];

export class WorksShell extends Component {
    static template = "ages_works_desk.WorksShell";
    static props = { ...standardActionServiceProps };
    static screenKey = "today";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this.state = useState({
            screenKey: this.constructor.screenKey,
            loading: true,
            error: false,
            options: { companies: [], sub_companies: [], projects: [], partners: [], contracts: [] },
            payload: {
                queues: [],
                columns: [],
                rows: [],
                inspector: false,
                features: {},
                hint: false,
            },
            filters: {
                company_ids: [],
                sub_company_ids: [],
                project_id: false,
                partner_id: false,
                contract_id: false,
                date_to: false,
                queue_key: false,
                selected_id: false,
                sort_key: "remaining_ra",
                sort_dir: "desc",
            },
        });
        onWillStart(async () => {
            await this.loadOptions();
            await this.reload();
        });
        useExternalListener(window, "keydown", this.onKeydown.bind(this));
    }

    get screens() {
        return WORKS_SCREENS;
    }

    get screenKey() {
        return this.state.screenKey;
    }

    get screenTitle() {
        return SCREEN_META[this.screenKey].title;
    }

    get rpcMethod() {
        return SCREEN_META[this.screenKey].method;
    }

    get companySelectValue() {
        const ids = this.state.filters.company_ids || [];
        return ids.length === 1 ? String(ids[0]) : "";
    }

    get subCompanySelectValue() {
        const ids = this.state.filters.sub_company_ids || [];
        return ids.length === 1 ? String(ids[0]) : "";
    }

    rpcFilters() {
        const filters = { ...this.state.filters };
        if (filters.project_id) {
            filters.project_ids = [filters.project_id];
        }
        if (filters.partner_id) {
            filters.partner_ids = [filters.partner_id];
        }
        if (filters.contract_id) {
            filters.contract_ids = [filters.contract_id];
        }
        return filters;
    }

    async loadOptions() {
        const options = await this.orm.call("ages.works.desk", "get_filter_options", [this.rpcFilters()]);
        this.state.options = options;
        if (!this.state.filters.company_ids.length && options.companies.length) {
            this.state.filters.company_ids = options.companies.map((c) => c.id);
        }
    }

    async reload() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const payload = await this.orm.call("ages.works.desk", this.rpcMethod, [this.rpcFilters()]);
            this.state.payload = payload;
            if (payload.active_queue && this.state.filters.queue_key !== payload.active_queue) {
                const keys = (payload.queues || []).map((q) => q.key);
                if (!keys.includes(this.state.filters.queue_key)) {
                    this.state.filters.queue_key = payload.active_queue;
                }
            }
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || "Unable to load Works Desk.";
            this.state.payload = { queues: [], columns: [], rows: [], inspector: false, features: {}, hint: false };
        }
        this.state.loading = false;
    }

    async onFilterChange() {
        this.state.filters.selected_id = false;
        this.state.filters.queue_key = false;
        await this.loadOptions();
        await this.reload();
    }

    async switchScreen(key) {
        if (this.state.screenKey === key) {
            return;
        }
        this.state.screenKey = key;
        this.state.filters.queue_key = false;
        this.state.filters.selected_id = false;
        await this.reload();
    }

    onCompanyChange(ev) {
        const value = ev.target.value;
        this.state.filters.company_ids = value
            ? [parseInt(value, 10)]
            : this.state.options.companies.map((c) => c.id);
        this.state.filters.sub_company_ids = [];
        this.state.filters.project_id = false;
        this.state.filters.contract_id = false;
        this.onFilterChange();
    }

    onSubCompanyChange(ev) {
        const value = ev.target.value;
        this.state.filters.sub_company_ids = value ? [parseInt(value, 10)] : [];
        this.state.filters.project_id = false;
        this.state.filters.contract_id = false;
        this.onFilterChange();
    }

    onProjectChange(ev) {
        this.state.filters.project_id = ev.target.value ? parseInt(ev.target.value, 10) : false;
        this.state.filters.contract_id = false;
        this.onFilterChange();
    }

    onPartnerChange(ev) {
        this.state.filters.partner_id = ev.target.value ? parseInt(ev.target.value, 10) : false;
        this.state.filters.contract_id = false;
        this.onFilterChange();
    }

    onContractChange(ev) {
        this.state.filters.contract_id = ev.target.value ? parseInt(ev.target.value, 10) : false;
        this.onFilterChange();
    }

    onDateChange(ev) {
        this.state.filters.date_to = ev.target.value || false;
        this.onFilterChange();
    }

    async selectQueue(queue) {
        this.state.filters.queue_key = queue.key;
        this.state.filters.selected_id = false;
        await this.reload();
    }

    openQueue(queue, event) {
        event.stopPropagation();
        if (queue.action) {
            this.action.doAction(queue.action);
        }
    }

    async selectRow(row) {
        this.state.filters.selected_id = row.id;
        await this.reload();
    }

    openAction(action) {
        if (action) {
            this.action.doAction(action);
        }
    }

    async sortBy(column) {
        if (!column.sort) {
            return;
        }
        if (this.state.filters.sort_key === column.sort) {
            this.state.filters.sort_dir = this.state.filters.sort_dir === "desc" ? "asc" : "desc";
        } else {
            this.state.filters.sort_key = column.sort;
            this.state.filters.sort_dir = "desc";
        }
        await this.reload();
    }

    cellValue(row, column) {
        const value = row[column.key];
        return value === false || value === undefined || value === null ? "" : value;
    }

    severityClass(queue) {
        return `aw-queue aw-sev-${queue.severity || "normal"}${
            queue.key === this.state.filters.queue_key ? " aw-selected" : ""
        }`;
    }

    screenClass(screen) {
        return `aw-tab${screen.key === this.state.screenKey ? " aw-selected" : ""}`;
    }

    onKeydown(ev) {
        const tag = (ev.target && ev.target.tagName) || "";
        if (["INPUT", "SELECT", "TEXTAREA"].includes(tag)) {
            return;
        }
        const rows = this.state.payload.rows || [];
        if (!rows.length) {
            return;
        }
        const currentId = this.state.filters.selected_id;
        const index = rows.findIndex((row) => row.id === currentId);
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            const next = rows[Math.min(index + 1, rows.length - 1)] || rows[0];
            this.selectRow(next);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            const prev = rows[Math.max(index - 1, 0)] || rows[0];
            this.selectRow(prev);
        } else if (ev.key === "Enter" && index >= 0) {
            ev.preventDefault();
            this.openAction(rows[index].action);
        } else if (ev.key === "Escape" && currentId) {
            this.state.filters.selected_id = false;
            this.reload();
        }
    }
}
