/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { formatMonetary } from "@web/views/fields/formatters";
import { ReportLineMenu } from "../report_line_menu/report_line_menu";
import {
    applyReportOptionalColumns,
    optionalColumnDefaults,
    ReportOptionalColumns,
} from "../report_optional_columns/report_optional_columns";
import {
    buildMoveLineListAction,
    rememberHighlightMoveLine,
} from "../report_navigation/report_navigation";
import {
    bootstrapReportWizard,
    setupReportPersistence,
    writeAndSyncFilters,
    cloneFilterValue,
} from "../report_state_utils/report_state_utils";
import { selectedRecordsFilterLabel } from "../report_filters/report_filters";

const OPTIONAL_COLUMNS = [
    { id: "invoice_date", label: "Invoice Date" },
    { id: "currency", label: "Amount Currency" },
    { id: "account", label: "Account" },
];
const PERSISTED_FILTERS = [
    "dateTo",
    "agingBasedOn",
    "agingInterval",
    "partnerIds",
    "partnerNames",
    "partnerCategoryIds",
    "filterTrade",
    "filterNonTrade",
    "allEntries",
    "showCurrency",
    "showAccount",
    "hideZeroLines",
    "sortBy",
    "sortDirection",
    "optionalColumns",
];

const FILTER_DEFAULTS = {
    dateTo: "",
    agingBasedOn: "maturity",
    agingInterval: 30,
    partnerIds: [],
    partnerNames: [],
    partnerCategoryIds: [],
    filterTrade: true,
    filterNonTrade: false,
    allEntries: false,
    showCurrency: false,
    showAccount: false,
    hideZeroLines: false,
    sortBy: "name",
    sortDirection: "asc",
    optionalColumns: optionalColumnDefaults(OPTIONAL_COLUMNS.filter((col) => col.id === "invoice_date")),
};

export class AgesAgedPartnerBalanceReport extends Component {
    static template = "ages_custom_reports.AgesAgedPartnerBalanceReport";
    static components = { Layout, MultiRecordSelector, ReportLineMenu, ReportOptionalColumns };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.reportType = this.props.action?.params?.report_type || "receivable";
        this.rootRef = useRef("root");
        this.dateBtn = useRef("dateBtn");
        this.accountFilterBtnRef = useRef("accountFilterBtn");
        this.partnerBtn = useRef("partnerBtn");
        this.basisBtn = useRef("basisBtn");
        this.intervalBtn = useRef("intervalBtn");
        this.optionsBtn = useRef("optionsBtn");
        this.gearBtnRef = useRef("gearBtn");

        const persistence = setupReportPersistence(this.props, {
            filterFields: PERSISTED_FILTERS,
            filterDefaults: FILTER_DEFAULTS,
            detailCacheField: "partnerDetails",
            reportKey: `ages_aged_partner_balance_${this.reportType}`,
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
            unfoldAll: persistence.savedUi.unfoldAll ?? false,
            lines: [],
            columns: [],
            periodLabels: {},
            warnings: [],
            title: this.reportType === "payable" ? "Aged Payable" : "Aged Receivable",
            currencyId: false,
            currencyLabel: "",
            dateLabel: "",
            multiCurrency: false,
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
            partnerDetails: persistence.savedUi.detailCache,
            loadingPartners: {},
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
        });
        this._requestNumber = 0;
        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);

        this._onDocumentClick = (ev) => {
            if (!this.state.openMenu) {
                return;
            }
            if (
                ev.target.closest(
                    ".o_ages_apb_dropdown, .o-autocomplete, .o-autocomplete--dropdown-menu, .o_input_dropdown, .o-overlay-item, .o-dropdown--menu, .o_multi_record_selector, .o_ages_optional_columns"
                )
            ) {
                return;
            }
            const triggerRefs = [
                this.dateBtn,
                this.accountFilterBtnRef,
                this.partnerBtn,
                this.basisBtn,
                this.intervalBtn,
                this.optionsBtn,
                this.gearBtnRef,
            ];
            if (triggerRefs.some((ref) => ref.el?.contains(ev.target))) {
                return;
            }
            this.state.openMenu = null;
        };

        onMounted(() => {
            document.addEventListener("click", this._onDocumentClick, true);
        });
        onWillUnmount(() => {
            document.removeEventListener("click", this._onDocumentClick, true);
        });

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "aged.partner.balance.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                createArgs: [{ report_type: this.reportType }],
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "aged.partner.balance.wizard",
                        "get_filter_values",
                        [this.state.wizardId]
                    );
                    this._loadFilters(filters);
                },
                state: this.state,
                persistFilters: (state) => this._reportPersistence?.persistFilters(state),
            });
            await this.refreshReport({ preserveUiState: restoring });
            this._restoringUiState = false;
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get accountFilterLabel() {
        const typeLabel = this.reportType === "payable" ? "Payable" : "Receivable";
        const choices = [];
        if (this.state.filterTrade) {
            choices.push(typeLabel);
        }
        if (this.state.filterNonTrade) {
            choices.push(`Non-Trade ${typeLabel}`);
        }
        return choices.length ? `Account: ${choices.join(", ")}` : "Account";
    }

    get formattedAsOf() {
        if (!this.state.dateTo) {
            return "";
        }
        try {
            return formatDate(deserializeDate(this.state.dateTo));
        } catch {
            return this.state.dateTo;
        }
    }

    get dateFilterLabel() {
        return this.formattedAsOf ? `As of ${this.formattedAsOf}` : "As of";
    }

    get agingBasisLabel() {
        return this.state.agingBasedOn === "invoice" ? "Invoice Date" : "Due Date";
    }

    get optionsFilterLabel() {
        return this.state.allEntries ? "With Draft Entries" : "Posted Entries";
    }

    get partnerDomain() {
        return ["|", ["parent_id", "=", false], ["is_company", "=", true]];
    }

    get partnerFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.partnerNames,
            "All Partners",
            this.state.partnerIds
        );
    }

    get partnerSearchLabel() {
        return selectedRecordsFilterLabel(
            this.state.partnerNames,
            "",
            this.state.partnerIds
        );
    }

    get displayedColumns() {
        return (this.state.columns || []).filter((column) => {
            if (column.key === "invoice_date") {
                return this.isColumnVisible("invoice_date");
            }
            return true;
        });
    }

    get optionalColumnDefs() {
        const columns = [{ id: "invoice_date", label: "Invoice Date" }];
        if (this.state.multiCurrency) {
            columns.push({ id: "currency", label: "Amount Currency" });
        }
        columns.push({ id: "account", label: "Account" });
        return columns;
    }

    get optionalColumnVisible() {
        return {
            ...(this.state.optionalColumns || {}),
            currency: this.state.showCurrency,
            account: this.state.showAccount,
        };
    }

    get tagSearchLabel() {
        const count = this.state.partnerCategoryIds.length;
        return count ? `${count} selected` : "";
    }

    get visibleLines() {
        return this._flattenLines(this.state.lines);
    }

    getPartnerDomain() {
        return this.partnerDomain;
    }

    getCategoryDomain() {
        return [];
    }

    menuStyle() {
        return `top: ${this.state.menuTop}px; left: ${this.state.menuLeft}px;`;
    }

    _loadFilters(filters) {
        if (this._restoringUiState) {
            return;
        }
        this.state.dateTo = filters.date_to || "";
        this.state.agingBasedOn = filters.aging_based_on || "maturity";
        this.state.agingInterval = filters.aging_interval || 30;
        this.state.partnerIds = filters.partner_ids || [];
        this.state.partnerNames = filters.partner_names || [];
        this.state.partnerCategoryIds = filters.partner_category_ids || [];
        this.state.filterTrade = filters.filter_trade !== false;
        this.state.filterNonTrade = !!filters.filter_non_trade;
        this.state.allEntries = !!filters.all_entries;
        this.state.showCurrency = !!filters.show_currency;
        this.state.showAccount = !!filters.show_account;
        this.state.hideZeroLines = !!filters.hide_zero_lines;
        this.state.sortBy = filters.sort_by || "name";
        this.state.sortDirection = filters.sort_direction || "asc";
        this.state.unfoldAll = !!filters.unfold_all;
    }

    _filterPayload() {
        return {
            report_type: this.reportType,
            date_to: this.state.dateTo || false,
            aging_based_on: this.state.agingBasedOn,
            aging_interval: Math.max(Number(this.state.agingInterval) || 30, 1),
            partner_ids: this.state.partnerIds,
            partner_category_ids: this.state.partnerCategoryIds,
            filter_trade: this.state.filterTrade,
            filter_non_trade: this.state.filterNonTrade,
            all_entries: this.state.allEntries,
            show_currency: this.state.showCurrency,
            show_account: this.state.showAccount,
            hide_zero_lines: this.state.hideZeroLines,
            unfold_all: this.state.unfoldAll,
            sort_by: this.state.sortBy,
            sort_direction: this.state.sortDirection,
        };
    }

    _partnerKey(line) {
        return line.partner_id || "none";
    }

    _getPartnerChildren(line) {
        const key = this._partnerKey(line);
        if (this.state.partnerDetails[key]) {
            return this.state.partnerDetails[key];
        }
        return line.children || [];
    }

    _flattenLines(lines) {
        const result = [];
        for (const line of lines) {
            result.push(line);
            if (!line.foldable || !this.isExpanded(line)) {
                continue;
            }
            result.push(...this._getPartnerChildren(line));
        }
        return result;
    }

    async clearFilters() {
        this.state.openMenu = null;
        const defaults = this._reportPersistence?.filterDefaults || FILTER_DEFAULTS;
        for (const [field, defaultValue] of Object.entries(defaults)) {
            if (!(field in this.state)) {
                continue;
            }
            this.state[field] = cloneFilterValue(defaultValue);
        }
        this.state.expandedIds = {};
        this.state.partnerDetails = {};
        this.state.lineSearch = "";
        await this.refreshReport();
    }

    async refreshReport(options = {}) {
        this._reportPersistence?.persistFilters(this.state);
        const requestNumber = ++this._requestNumber;
        const preserveUi = options.preserveUiState;
        const savedExpanded = preserveUi ? { ...this.state.expandedIds } : {};
        const savedDetails = preserveUi ? { ...this.state.partnerDetails } : {};

        this.state.loading = true;
        if (!preserveUi) {
            this.state.partnerDetails = {};
        }
        try {
            await writeAndSyncFilters(
                this.orm,
                "aged.partner.balance.wizard",
                this.state.wizardId,
                this._filterPayload(),
                this.state,
                (state) => this._reportPersistence?.persistFilters(state),
            );
            const data = await this.orm.call(
                "aged.partner.balance.wizard",
                "get_report_lines",
                [this.state.wizardId]
            );
            if (requestNumber !== this._requestNumber) {
                return;
            }
            this.state.lines = data.lines || [];
            this.state.columns = data.columns || [];
            this.state.periodLabels = data.period_labels || {};
            this.state.warnings = data.warnings || [];
            this.state.title = data.title || this.state.title;
            this.state.currencyId = data.currency_id || false;
            this.state.currencyLabel = data.currency_label || "";
            this.state.dateLabel = data.date_label || this.state.dateTo;
            this.state.multiCurrency = !!data.multi_currency;

            if (preserveUi) {
                this.state.expandedIds = savedExpanded;
                this.state.partnerDetails = savedDetails;
                await this._ensureExpandedPartnerDetails();
            } else if (this.state.unfoldAll) {
                for (const line of this.state.lines) {
                    if (line.line_type === "partner" && line.children?.length) {
                        this.state.partnerDetails[this._partnerKey(line)] = line.children;
                    }
                }
            }
        } finally {
            if (requestNumber === this._requestNumber) {
                this.state.loading = false;
            }
        }
    }

    async _loadPartnerDetail(partnerId) {
        const key = partnerId || "none";
        const result = await this.orm.call(
            "aged.partner.balance.wizard",
            "get_partner_detail",
            [this.state.wizardId, partnerId || false]
        );
        this.state.partnerDetails = {
            ...this.state.partnerDetails,
            [key]: result.children || [],
        };
    }

    async _ensureExpandedPartnerDetails() {
        for (const line of this.state.lines) {
            if (
                line.line_type === "partner" &&
                this.isExpanded(line) &&
                !this.state.partnerDetails[this._partnerKey(line)]
            ) {
                await this._loadPartnerDetail(line.partner_id);
            }
        }
    }

    isExpanded(line) {
        if (!line.foldable) {
            return false;
        }
        if (line.id in this.state.expandedIds) {
            return this.state.expandedIds[line.id];
        }
        return this.state.unfoldAll;
    }

    async toggleFold(line) {
        if (!line.foldable) {
            return;
        }
        const next = !this.isExpanded(line);
        this.state.expandedIds = {
            ...this.state.expandedIds,
            [line.id]: next,
        };
        if (next && line.line_type === "partner") {
            const key = this._partnerKey(line);
            if (!this.state.partnerDetails[key]) {
                this.state.loadingPartners = {
                    ...this.state.loadingPartners,
                    [key]: true,
                };
                try {
                    await this._loadPartnerDetail(line.partner_id);
                } finally {
                    this.state.loadingPartners = {
                        ...this.state.loadingPartners,
                        [key]: false,
                    };
                }
            }
        }
    }

    isPartnerLoading(line) {
        return (
            line.line_type === "partner" &&
            this.state.loadingPartners[this._partnerKey(line)]
        );
    }

    formatAmount(amount) {
        if (amount === false || amount === null || amount === undefined) {
            return "";
        }
        if (!this.state.currencyId) {
            return Number(amount).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }
        return formatMonetary(amount, { currencyId: this.state.currencyId });
    }

    formatOriginalAmount(amount) {
        if (amount === false || amount === null || amount === undefined) {
            return "";
        }
        return Number(amount).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    displayCell(line, column) {
        const value = line[column.key];
        if (column.type === "monetary") {
            if (value === false || value === null || value === undefined) {
                return "";
            }
            return this.formatAmount(value);
        }
        if (column.type === "amount_currency") {
            if (value === false || value === null || value === undefined) {
                return "";
            }
            return this.formatOriginalAmount(value);
        }
        if (column.type === "date") {
            if (!value) {
                return "";
            }
            try {
                return formatDate(deserializeDate(value));
            } catch {
                return value;
            }
        }
        return value || "";
    }

    amountClass(value) {
        if (value === false || value === null || value === undefined) {
            return "";
        }
        if (value < 0) {
            return "text-danger";
        }
        if (!value) {
            return "muted";
        }
        return "";
    }

    columnClass(column, line) {
        const classes = [];
        if (column.type === "date") {
            classes.push("date");
        }
        if (column.type === "monetary" || column.type === "amount_currency") {
            classes.push("numeric", "text-end");
            classes.push(this.amountClass(line[column.key]));
        }
        if (this.isAuditableCell(line, column)) {
            classes.push("auditable");
        }
        return classes.filter(Boolean).join(" ");
    }

    headerCellClass(column) {
        if (column.type === "date") {
            return "date";
        }
        if (column.type === "monetary" || column.type === "amount_currency") {
            return "numeric text-end";
        }
        return "";
    }

    rowClass(line) {
        const classes = ["o_ages_report_row"];
        if (line.line_type === "total") {
            classes.push("o_ages_apb_row-total", "line_level_0", "total");
        } else if (line.line_type === "partner") {
            classes.push("o_ages_apb_row-partner", "line_level_1");
        } else if (line.line_type === "move_line") {
            classes.push("o_ages_apb_row-detail", "line_level_2");
        }
        if (line.foldable && this.isExpanded(line)) {
            classes.push("unfolded", "o_ages_row-unfolded");
        }
        return classes.join(" ");
    }

    isAuditableCell(line, column) {
        return (
            line.line_type === "partner" &&
            column.auditable &&
            line[column.key] !== false &&
            line[column.key] !== null &&
            line[column.key] !== undefined &&
            line[column.key] !== 0
        );
    }

    async sortBy(columnKey) {
        if (this.state.sortBy === columnKey) {
            this.state.sortDirection =
                this.state.sortDirection === "asc" ? "desc" : "asc";
        } else {
            this.state.sortBy = columnKey;
            this.state.sortDirection = columnKey === "name" ? "asc" : "desc";
        }
        await this.refreshReport({ preserveUiState: true });
    }

    sortIcon(columnKey) {
        if (this.state.sortBy !== columnKey) {
            return "fa fa-long-arrow-up";
        }
        return this.state.sortDirection === "asc"
            ? "fa fa-long-arrow-up"
            : "fa fa-long-arrow-down";
    }

    toggleMenu(menuName, ev) {
        ev.stopPropagation();
        const next = this.state.openMenu === menuName ? null : menuName;
        this.state.openMenu = next;
        if (next) {
            const rect = ev.currentTarget.getBoundingClientRect();
            this.state.menuTop = rect.bottom + 4;
            this.state.menuLeft = rect.left;
        }
    }

    toggleBoolean(fieldName) {
        this.state[fieldName] = !this.state[fieldName];
        this.debouncedRefresh();
    }

    setAgingBasis(value) {
        this.state.agingBasedOn = value;
        this.state.openMenu = null;
        this.debouncedRefresh();
    }

    onBooleanFilterChange(fieldName, ev) {
        this.state[fieldName] = ev.target.checked;
        this.debouncedRefresh();
    }

    onDateChange(ev) {
        this.state.dateTo = ev.target.value;
        this.debouncedRefresh();
    }

    onAgingBasisChange(ev) {
        this.state.agingBasedOn = ev.target.value;
        this.debouncedRefresh();
    }

    onIntervalChange(ev) {
        this.state.agingInterval = Math.max(Number(ev.target.value) || 30, 1);
        this.debouncedRefresh();
    }

    async onPartnerUpdate(resIds) {
        this.state.partnerIds = resIds || [];
        if (this.state.partnerIds.length) {
            const records = await this.orm.read(
                "res.partner",
                this.state.partnerIds,
                ["display_name"]
            );
            this.state.partnerNames = records.map((r) => r.display_name || "");
        } else {
            this.state.partnerNames = [];
        }
        this.debouncedRefresh();
    }

    onPartnerCategoryUpdate(resIds) {
        this.state.partnerCategoryIds = resIds || [];
        this.debouncedRefresh();
    }

    onToggleUnfoldAll() {
        this.state.unfoldAll = !this.state.unfoldAll;
        this.state.expandedIds = {};
        this.refreshReport();
    }

    onUnfoldAllChange(ev) {
        this.state.unfoldAll = ev.target.checked;
        this.state.expandedIds = {};
        this.state.openMenu = null;
        this.refreshReport();
    }

    _runAction(action) {
        if (action?.type) {
            return this.actionService.doAction(action);
        }
    }

    async onPrintPdf() {
        await this.refreshReport({ preserveUiState: true });
        const action = await this.orm.call(
            "aged.partner.balance.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport({ preserveUiState: true });
        const action = await this.orm.call(
            "aged.partner.balance.wizard",
            "action_print_excel",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async openPartner(line) {
        if (!line.partner_id) {
            return;
        }
        const action = await this.orm.call(
            "aged.partner.balance.wizard",
            "action_open_partner",
            [[this.state.wizardId], line.partner_id]
        );
        await this._runAction(action);
    }

    async openPartnerLedger(line) {
        if (!line.partner_id) {
            return;
        }
        const action = await this.orm.call(
            "aged.partner.balance.wizard",
            "action_open_partner_ledger",
            [[this.state.wizardId], line.partner_id]
        );
        await this._runAction(action);
    }

    async openBucket(line, column) {
        if (!this.isAuditableCell(line, column)) {
            return;
        }
        const action = await this.orm.call(
            "aged.partner.balance.wizard",
            "action_open_bucket",
            [[this.state.wizardId], line.partner_id || false, column.key]
        );
        await this._runAction(action);
    }

    async openJournalItems(line) {
        const action = await this.orm.call(
            "aged.partner.balance.wizard",
            "action_open_bucket",
            [[this.state.wizardId], line.partner_id || false, "total"]
        );
        await this._runAction(action);
    }

    async openJournalEntry(line) {
        if (!line.move_id) {
            return;
        }
        const action = await this.orm.call(
            "aged.partner.balance.wizard",
            "action_open_journal_entry",
            [[this.state.wizardId], line.move_id, line.move_line_id || false]
        );
        rememberHighlightMoveLine(line.move_line_id);
        await this._runAction(action);
    }

    openMoveJournalItems(line) {
        if (!line.move_id) {
            return;
        }
        return this._runAction(buildMoveLineListAction({
            name: `${line.name} — Journal Items`,
            domain: [["move_id", "=", line.move_id]],
            highlightMoveLineId: line.move_line_id,
        }));
    }

    getMoveLineMenuItems(line) {
        if (line.line_type !== "move_line" || !line.move_id) {
            return [];
        }
        return [{
            label: "View Journal Entry",
            onClick: () => this.openJournalEntry(line),
        }, {
            label: "Journal Items",
            onClick: () => this.openMoveJournalItems(line),
        }];
    }

    onOptionalColumnToggle(columnId) {
        if (columnId === "currency") {
            this.toggleBoolean("showCurrency");
            return true;
        }
        if (columnId === "account") {
            this.toggleBoolean("showAccount");
            return true;
        }
        return false;
    }
}

applyReportOptionalColumns(AgesAgedPartnerBalanceReport);

registry
    .category("actions")
    .add("ages_aged_partner_balance_report", AgesAgedPartnerBalanceReport);
