/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { formatMonetary } from "@web/views/fields/formatters";
import { user } from "@web/core/user";
import {
    bootstrapReportWizard,
    setupReportPersistence,
    writeAndSyncFilters,
} from "@ages_custom_reports/report_state_utils/report_state_utils";
import {
    setupReportFilterMenus,
    selectedRecordsFilterLabel,
} from "@ages_custom_reports/report_filters/report_filters";
import {
    applyReportOptionalColumns,
    optionalColumnDefaults,
} from "@ages_custom_reports/report_optional_columns/report_optional_columns";

const WIZARD_MODEL = "opal.report.wizard";
const ROW_HEIGHT = 34;
const ROW_BUFFER = 24;
const VIRTUALIZE_AFTER = 60;
const FILTER_OPTION_CAP = 80;
const TABS = [
    { id: "vendor_project", label: "Vendor by Project" },
    { id: "vendor_account", label: "By Account" },
    { id: "vendor_total", label: "Vendor Totals" },
    { id: "project_total", label: "Project Totals" },
];
const OPTIONAL_COLUMNS = [
    { id: "source", label: "Source", defaultVisible: true },
    { id: "vendor", label: "Vendor / Client", defaultVisible: true },
    { id: "project_code", label: "Project Code", defaultVisible: true },
    { id: "project_name", label: "Project Name", defaultVisible: true },
    { id: "category", label: "Category", defaultVisible: true },
    { id: "account_name", label: "Account Name", defaultVisible: true },
    { id: "projects", label: "Projects", defaultVisible: true },
    { id: "vendors", label: "Vendors", defaultVisible: true },
    { id: "debit", label: "Debit", defaultVisible: true },
    { id: "credit", label: "Credit", defaultVisible: true },
    { id: "balance", label: "Balance", defaultVisible: true },
    { id: "variance", label: "Variance", defaultVisible: true },
];
const PERSISTED_FILTERS = [
    "tab",
    "asOf",
    "vendorNames",
    "projectCodes",
    "accountNames",
    "lineSearch",
    "showZeroLines",
    "showOdooOverall",
    "showUnmappedOnly",
    "optionalColumns",
];
const FILTER_DEFAULTS = {
    tab: "vendor_project",
    asOf: "",
    vendorNames: [],
    projectCodes: [],
    accountNames: [],
    lineSearch: "",
    showZeroLines: true,
    showOdooOverall: false,
    showUnmappedOnly: false,
    optionalColumns: optionalColumnDefaults(OPTIONAL_COLUMNS),
};
const TOTAL_SOURCE = {
    vendor_project: "opal_project",
    vendor_account: "opal_account",
    vendor_total: "opal_vendor_total",
    project_total: "opal_project_total",
};

function sumField(rows, field) {
    return rows.reduce((total, row) => total + (Number(row[field]) || 0), 0);
}

function searchBlob(parts) {
    return parts.filter(Boolean).join(" ").toLowerCase();
}

function filterVendorProject(lines, state, accountIndex) {
    const vendors = new Set(state.vendorNames || []);
    const projects = new Set(state.projectCodes || []);
    const accounts = new Set(state.accountNames || []);
    const search = (state.lineSearch || "").trim().toLowerCase();
    const groups = [];
    let current = null;
    for (const line of lines) {
        if (line.source === "odoo_overall") {
            current = { odoo: line, opal: null, projects: [] };
            groups.push(current);
        } else if (line.source === "opal_overall") {
            if (current) {
                current.opal = line;
            }
        } else if (current) {
            current.projects.push(line);
        }
    }
    const result = [];
    for (const group of groups) {
        if (vendors.size && !vendors.has(group.odoo.vendor)) {
            continue;
        }
        if (state.showUnmappedOnly && group.odoo.mapped) {
            continue;
        }
        let projectRows = group.projects;
        if (search) {
            const vendorHit = (group.odoo.vendor || "").toLowerCase().includes(search);
            const matching = projectRows.filter((row) =>
                searchBlob([group.odoo.vendor, row.project_code, row.project_name]).includes(search)
            );
            if (!vendorHit && !matching.length) {
                continue;
            }
            if (!vendorHit) {
                projectRows = matching;
            }
        }
        if (projects.size) {
            projectRows = projectRows.filter((row) => projects.has(row.project_code));
            if (!projectRows.length) {
                continue;
            }
        }
        if (accounts.size) {
            projectRows = projectRows.filter((row) => {
                const names = accountIndex[`${row.vendor}\t${row.project_code}`] || [];
                return names.some((name) => accounts.has(name));
            });
            if (!projectRows.length) {
                continue;
            }
        }
        if (!state.showZeroLines) {
            projectRows = projectRows.filter((row) => row.balance);
            if (!projectRows.length) {
                continue;
            }
        }
        const opalDebit = sumField(projectRows, "debit");
        const opalCredit = sumField(projectRows, "credit");
        const opalBalance = sumField(projectRows, "balance");
        result.push({
            ...group.odoo,
            variance: (group.odoo.balance || 0) - opalBalance,
        });
        if (group.opal) {
            result.push({
                ...group.opal,
                debit: opalDebit,
                credit: opalCredit,
                balance: opalBalance,
            });
        }
        result.push(...projectRows);
    }
    return result;
}

function filterVendorAccount(lines, state) {
    const vendors = new Set(state.vendorNames || []);
    const projects = new Set(state.projectCodes || []);
    const accounts = new Set(state.accountNames || []);
    const search = (state.lineSearch || "").trim().toLowerCase();
    return lines.filter((line) => {
        if (vendors.size && !vendors.has(line.vendor)) {
            return false;
        }
        if (projects.size && !projects.has(line.project_code)) {
            return false;
        }
        if (accounts.size && !accounts.has(line.account_name)) {
            return false;
        }
        if (state.showUnmappedOnly && line.mapped) {
            return false;
        }
        if (!state.showZeroLines && !line.balance) {
            return false;
        }
        if (search && !searchBlob([
            line.vendor, line.project_code, line.project_name, line.category, line.account_name,
        ]).includes(search)) {
            return false;
        }
        return true;
    });
}

function filterVendorTotal(lines, state) {
    const vendors = new Set(state.vendorNames || []);
    const search = (state.lineSearch || "").trim().toLowerCase();
    const showOdoo = state.showOdooOverall || vendors.size || search;
    const result = [];
    for (const line of lines) {
        if (vendors.size && !vendors.has(line.vendor)) {
            continue;
        }
        if (state.showUnmappedOnly && line.mapped) {
            continue;
        }
        if (search && !(line.vendor || "").toLowerCase().includes(search)) {
            continue;
        }
        if (line.source === "odoo_overall" && !showOdoo) {
            continue;
        }
        result.push(line);
    }
    return result;
}

function filterProjectTotal(lines, state) {
    const vendors = new Set(state.vendorNames || []);
    const projects = new Set(state.projectCodes || []);
    const search = (state.lineSearch || "").trim().toLowerCase();
    return lines.filter((line) => {
        if (projects.size && !projects.has(line.project_code)) {
            return false;
        }
        if (!state.showZeroLines && !line.balance) {
            return false;
        }
        if (search && !searchBlob([line.project_code, line.project_name]).includes(search)) {
            return false;
        }
        if (vendors.size && line.vendor && !vendors.has(line.vendor)) {
            return false;
        }
        return true;
    });
}

function filterLines(lines, tab, state, accountIndex) {
    if (tab === "vendor_account") {
        return filterVendorAccount(lines, state);
    }
    if (tab === "vendor_total") {
        return filterVendorTotal(lines, state);
    }
    if (tab === "project_total") {
        return filterProjectTotal(lines, state);
    }
    return filterVendorProject(lines, state, accountIndex);
}

function lineTotals(lines, tab) {
    const source = TOTAL_SOURCE[tab] || "opal_project";
    const chosen = lines.filter((line) => line.source === source);
    return {
        debit: sumField(chosen, "debit"),
        credit: sumField(chosen, "credit"),
        balance: sumField(chosen, "balance"),
    };
}

function capOptions(items, query) {
    if (query || items.length <= FILTER_OPTION_CAP) {
        return items;
    }
    return items.slice(0, FILTER_OPTION_CAP);
}

export class OpalVendorBalanceReport extends Component {
    static template = "ages_opal_vendor_balance.OpalVendorBalanceReport";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.rootRef = useRef("root");
        this.scrollRef = useRef("scroll");
        this.tabs = TABS;
        this.canImport = false;
        this._datasets = {};
        this._fetchGen = 0;
        this._amountCache = new Map();
        const persistence = setupReportPersistence(this.props, {
            filterFields: PERSISTED_FILTERS,
            filterDefaults: FILTER_DEFAULTS,
        });
        this._reportPersistence = persistence;
        this._restoringUiState = persistence.restoring;

        useSetupAction({
            rootRef: this.rootRef,
            getLocalState: () => persistence.getLocalState(this.state),
        });

        this.state = useState({
            wizardId: persistence.savedUi.wizardId || null,
            ...persistence.filterState,
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
            optionSearch: "",
            lines: [],
            columns: [],
            totals: { debit: 0, credit: 0, balance: 0 },
            currencyId: false,
            loading: false,
            hasData: false,
            vendorOptions: [],
            projectOptions: [],
            accountOptions: [],
            scrollTop: 0,
            viewportHeight: 640,
        });

        this.debouncedRefresh = debounce(() => this.applyLocalFilters(), 80);
        this.debouncedWizardSync = debounce(() => this.syncWizard(), 800);
        setupReportFilterMenus(this);

        onWillStart(async () => {
            this.canImport = await user.hasGroup("account.group_account_manager");
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: WIZARD_MODEL,
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(WIZARD_MODEL, "get_filter_values", [
                        this.state.wizardId,
                    ]);
                    this._loadFilters(filters);
                },
                state: this.state,
                persistFilters: (state) => this._reportPersistence?.persistFilters(state),
            });
            await this.refreshReport();
            this._restoringUiState = false;
        });

        onMounted(() => {
            this._syncViewport();
            this._onResize = () => this._syncViewport();
            window.addEventListener("resize", this._onResize);
        });
        onWillUnmount(() => {
            window.removeEventListener("resize", this._onResize);
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get vendorFilterLabel() {
        return selectedRecordsFilterLabel(this.state.vendorNames, "Vendors / Clients");
    }

    get projectFilterLabel() {
        return selectedRecordsFilterLabel(this.state.projectCodes, "Projects");
    }

    get accountFilterLabel() {
        return selectedRecordsFilterLabel(this.state.accountNames, "Accounts");
    }

    get asOfLabel() {
        return this.state.asOf ? `As of ${this.state.asOf}` : "As of";
    }

    get optionalColumnDefs() {
        const ids = new Set((this.state.columns || []).map((column) => column.id));
        if (!ids.size) {
            return OPTIONAL_COLUMNS;
        }
        return OPTIONAL_COLUMNS.filter((column) => ids.has(column.id));
    }

    get visibleColumns() {
        return (this.state.columns || []).filter((column) => this.isColumnVisible(column.id));
    }

    get columnsFilterLabel() {
        const hidden = this.optionalColumnDefs.filter((column) => !this.isColumnVisible(column.id)).length;
        return hidden ? `Columns · ${hidden} hidden` : "Columns";
    }

    get hiddenColumnIds() {
        return OPTIONAL_COLUMNS
            .filter((column) => !this.isColumnVisible(column.id))
            .map((column) => column.id);
    }

    get visibleVendorOptions() {
        const query = (this.state.optionSearch || "").toLowerCase();
        const items = (this.state.vendorOptions || []).filter((name) =>
            name.toLowerCase().includes(query)
        );
        return capOptions(items, query);
    }

    get vendorOptionsCapped() {
        const query = (this.state.optionSearch || "").toLowerCase();
        return !query && (this.state.vendorOptions || []).length > FILTER_OPTION_CAP;
    }

    get visibleProjectOptions() {
        const query = (this.state.optionSearch || "").toLowerCase();
        const items = (this.state.projectOptions || []).filter((item) =>
            `${item.code} ${item.name}`.toLowerCase().includes(query)
        );
        return capOptions(items, query);
    }

    get visibleAccountOptions() {
        const query = (this.state.optionSearch || "").toLowerCase();
        const items = (this.state.accountOptions || []).filter((name) =>
            name.toLowerCase().includes(query)
        );
        return capOptions(items, query);
    }

    get windowedLines() {
        const lines = this.state.lines || [];
        if (lines.length <= VIRTUALIZE_AFTER) {
            return lines;
        }
        const start = Math.max(0, Math.floor(this.state.scrollTop / ROW_HEIGHT) - ROW_BUFFER);
        const count = Math.ceil((this.state.viewportHeight || 640) / ROW_HEIGHT) + ROW_BUFFER * 2;
        return lines.slice(start, start + count);
    }

    get windowPad() {
        const lines = this.state.lines || [];
        if (lines.length <= VIRTUALIZE_AFTER) {
            return { top: 0, bottom: 0 };
        }
        const start = Math.max(0, Math.floor(this.state.scrollTop / ROW_HEIGHT) - ROW_BUFFER);
        const count = Math.ceil((this.state.viewportHeight || 640) / ROW_HEIGHT) + ROW_BUFFER * 2;
        const end = Math.min(lines.length, start + count);
        return {
            top: start * ROW_HEIGHT,
            bottom: Math.max(0, (lines.length - end) * ROW_HEIGHT),
        };
    }

    toggleFilterMenu(menuName, ev) {
        ev.stopPropagation();
        const next = this.state.openMenu === menuName ? null : menuName;
        this.state.openMenu = next;
        this.state.optionSearch = "";
        if (next) {
            const rect = ev.currentTarget.getBoundingClientRect();
            this.state.menuTop = rect.bottom + 6;
            this.state.menuLeft = rect.left;
        }
    }

    filterMenuStyle() {
        const width = 360;
        let left = this.state.menuLeft || 8;
        const top = this.state.menuTop || 0;
        if (typeof window !== "undefined") {
            left = Math.min(left, window.innerWidth - width - 8);
            left = Math.max(8, left);
        }
        return `top: ${top}px; left: ${left}px;`;
    }

    _datasetKey() {
        return `${this.state.tab}|${this.state.asOf || ""}`;
    }

    _filterPayload() {
        return {
            tab: this.state.tab,
            as_of: this.state.asOf || false,
            vendor_names: this.state.vendorNames,
            project_codes: this.state.projectCodes,
            account_names: this.state.accountNames,
            line_search: this.state.lineSearch,
            show_zero_lines: this.state.showZeroLines,
            show_odoo_overall: this.state.showOdooOverall,
            show_unmapped_only: this.state.showUnmappedOnly,
            hidden_column_ids: this.hiddenColumnIds,
        };
    }

    _loadFilters(filters) {
        this.state.tab = filters.tab || this.state.tab;
        this.state.asOf = filters.as_of || this.state.asOf;
        this.state.vendorNames = filters.vendor_names || [];
        this.state.projectCodes = filters.project_codes || [];
        this.state.accountNames = filters.account_names || [];
        this.state.showZeroLines = filters.show_zero_lines !== false;
        this.state.showOdooOverall = !!filters.show_odoo_overall;
        this.state.showUnmappedOnly = !!filters.show_unmapped_only;
        this.state.vendorOptions = filters.vendor_options || this.state.vendorOptions;
        this.state.projectOptions = filters.project_options || this.state.projectOptions;
        this.state.accountOptions = filters.account_options || this.state.accountOptions;
    }

    _syncViewport() {
        const el = this.scrollRef.el;
        if (el) {
            this.state.viewportHeight = el.clientHeight || 640;
        }
    }

    applyLocalFilters() {
        const dataset = this._datasets[this._datasetKey()];
        if (!dataset) {
            return;
        }
        this.state.columns = dataset.columns;
        this.state.currencyId = dataset.currencyId;
        this.state.hasData = dataset.hasData;
        this.state.lines = filterLines(
            dataset.lines,
            this.state.tab,
            this.state,
            dataset.accountIndex
        );
        this.state.totals = lineTotals(this.state.lines, this.state.tab);
        this.state.scrollTop = 0;
        if (this.scrollRef.el) {
            this.scrollRef.el.scrollTop = 0;
        }
    }

    async syncWizard() {
        if (!this.state.wizardId) {
            return;
        }
        await writeAndSyncFilters(
            this.orm,
            WIZARD_MODEL,
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state)
        );
    }

    async refreshReport() {
        this._reportPersistence?.persistFilters(this.state);
        const key = this._datasetKey();
        if (this._datasets[key]) {
            this.applyLocalFilters();
            this.debouncedWizardSync();
            return;
        }
        const gen = ++this._fetchGen;
        this.state.loading = true;
        try {
            const data = await this.orm.call(WIZARD_MODEL, "get_report_data", [
                this.state.wizardId,
                {
                    tab: this.state.tab,
                    as_of: this.state.asOf || false,
                    full_dataset: true,
                },
            ]);
            if (gen !== this._fetchGen) {
                return;
            }
            this._datasets[key] = {
                lines: data.lines || [],
                columns: data.columns || [],
                currencyId: data.currency_id,
                hasData: !!data.has_data,
                accountIndex: data.account_index || {},
            };
            if (data.vendor_options) {
                this.state.vendorOptions = data.vendor_options;
                this.state.projectOptions = data.project_options || [];
                this.state.accountOptions = data.account_options || [];
            }
            if (data.as_of && !this.state.asOf) {
                this.state.asOf = data.as_of;
            }
            this.applyLocalFilters();
        } finally {
            if (gen === this._fetchGen) {
                this.state.loading = false;
            }
        }
        this.debouncedWizardSync();
    }

    onTableScroll(ev) {
        this.state.scrollTop = ev.currentTarget.scrollTop;
    }

    setTab(tab) {
        if (this.state.tab === tab) {
            return;
        }
        this.state.tab = tab;
        this.refreshReport();
    }

    onLineSearch(ev) {
        this.state.lineSearch = ev.target.value;
        this._reportPersistence?.persistFilters(this.state);
        this.debouncedRefresh();
        this.debouncedWizardSync();
    }

    onAsOfChange(ev) {
        this.state.asOf = ev.target.value;
        this.refreshReport();
    }

    toggleListValue(field, value) {
        const current = this.state[field] || [];
        this.state[field] = current.includes(value)
            ? current.filter((item) => item !== value)
            : [...current, value];
        this._reportPersistence?.persistFilters(this.state);
        this.applyLocalFilters();
        this.debouncedWizardSync();
    }

    isSelected(field, value) {
        return (this.state[field] || []).includes(value);
    }

    toggleOption(field) {
        this.state[field] = !this.state[field];
        this._reportPersistence?.persistFilters(this.state);
        this.applyLocalFilters();
        this.debouncedWizardSync();
    }

    onOptionalColumnToggle(columnId) {
        if (this.isColumnVisible(columnId) && this.visibleColumns.length <= 1) {
            this.notification.add("Keep at least one column visible.", { type: "warning" });
            return true;
        }
        return false;
    }

    toggleColumn(columnId) {
        const wasVisible = this.isColumnVisible(columnId);
        this.toggleOptionalColumn(columnId);
        if (this.isColumnVisible(columnId) === wasVisible) {
            return;
        }
        this.debouncedWizardSync();
    }

    formatAmount(amount) {
        if (amount === false || amount === null || amount === undefined || amount === "") {
            return "";
        }
        const key = `${amount}|${this.state.currencyId}`;
        const cached = this._amountCache.get(key);
        if (cached !== undefined) {
            return cached;
        }
        const formatted = this.state.currencyId
            ? formatMonetary(amount, { currencyId: this.state.currencyId })
            : Number(amount).toFixed(2);
        this._amountCache.set(key, formatted);
        return formatted;
    }

    amountClass(amount) {
        if (amount < 0) {
            return "ages-bs-amount-negative";
        }
        if (!amount) {
            return "ages-bs-amount-zero";
        }
        return "";
    }

    rowClass(line) {
        return `o_ages_opal_row o_ages_opal_row-${line.line_type || line.source}`;
    }

    cellValue(line, column) {
        if (column.id === "source") {
            return line.source_label || "";
        }
        return line[column.id];
    }

    badgeClass(line) {
        if (line.source === "odoo_overall") {
            return "o_ages_report_badge o_ages_opal_badge_odoo";
        }
        if (line.source === "opal_overall" || line.source === "opal_vendor_total") {
            return "o_ages_report_badge o_ages_opal_badge_opal";
        }
        return "o_ages_report_badge o_ages_opal_badge_project";
    }

    badgeLabel(line) {
        if (line.source === "odoo_overall") {
            return "Odoo";
        }
        if (line.source === "opal_overall" || line.source === "opal_vendor_total") {
            return "OPAL";
        }
        return "Project";
    }

    async onLineClick(line) {
        if (line.source === "odoo_overall" && line.partner_id) {
            const action = await this.orm.call(WIZARD_MODEL, "action_open_partner_ledger", [
                line.partner_id,
            ]);
            if (action) {
                this.actionService.doAction(action);
            }
            return;
        }
        if (line.project_id && line.source === "opal_project") {
            const action = await this.orm.call(WIZARD_MODEL, "action_open_project", [
                line.project_id,
            ]);
            if (action) {
                this.actionService.doAction(action);
            }
        }
    }

    async onPrintPdf() {
        await this.syncWizard();
        const action = await this.orm.call(WIZARD_MODEL, "action_print_pdf", [
            [this.state.wizardId],
        ]);
        if (action) {
            this.actionService.doAction(action);
        }
    }

    async onPrintExcel() {
        await this.syncWizard();
        const action = await this.orm.call(WIZARD_MODEL, "action_print_excel", [
            [this.state.wizardId],
        ]);
        if (action) {
            this.actionService.doAction(action);
        }
    }

    async onImport() {
        this._datasets = {};
        await this.actionService.doAction("ages_opal_vendor_balance.action_opal_import_wizard");
    }

    async onOpenMapping() {
        const action = await this.orm.call(WIZARD_MODEL, "action_open_vendor_mapping", []);
        if (action) {
            this.actionService.doAction(action);
        }
    }
}

applyReportOptionalColumns(OpalVendorBalanceReport);

registry.category("actions").add("opal_vendor_balance_report", OpalVendorBalanceReport);
