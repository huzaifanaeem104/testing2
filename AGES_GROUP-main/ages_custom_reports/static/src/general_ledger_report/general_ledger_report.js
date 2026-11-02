/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { formatMonetary } from "@web/views/fields/formatters";
import { ReportLineMenu } from "../report_line_menu/report_line_menu";
import {
    applyReportOptionalColumns,
    optionalColumnDefaults,
    ReportOptionalColumns,
} from "../report_optional_columns/report_optional_columns";
import {
    buildJournalEntryAction,
    buildJournalItemsForAccountAction,
    buildMoveLineListAction,
} from "../report_navigation/report_navigation";
import {
    bootstrapReportWizard,
    setupReportPersistence,
    writeAndSyncFilters,
} from "../report_state_utils/report_state_utils";
import {
    applyReportFilterMenus,
    setupReportFilterMenus,
    selectedRecordsFilterLabel,
} from "../report_filters/report_filters";
import { ledgerWindow, setupLedgerVirtualScroll } from "../report_virtual_rows/report_virtual_rows";

const OPTIONAL_COLUMNS = [
    { id: "date", label: "Date" },
    { id: "partner", label: "Partner" },
    { id: "currency", label: "Amount Currency" },
];
const PERSISTED_FILTERS = [
    "dateFrom", "dateTo", "targetMove", "journalIds", "journalNames",
    "accountIds", "accountNames", "analyticAccountId", "analyticAccountName",
    "optionalColumns",
];
const FILTER_DEFAULTS = {
    dateFrom: "",
    dateTo: "",
    targetMove: "posted",
    journalIds: [],
    journalNames: [],
    accountIds: [],
    accountNames: [],
    analyticAccountId: false,
    analyticAccountName: "",
    optionalColumns: optionalColumnDefaults(OPTIONAL_COLUMNS),
};

export class AgesGeneralLedgerReport extends Component {
    static template = "ages_custom_reports.AgesGeneralLedgerReport";
    static components = { Layout, ReportLineMenu, ReportOptionalColumns };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        const persistence = setupReportPersistence(this.props, {
            filterFields: PERSISTED_FILTERS,
            filterDefaults: FILTER_DEFAULTS,
            detailCacheField: "accountDetails",
        });
        this._reportPersistence = persistence;
        this._restoringUiState = persistence.restoring;

        useSetupAction({
            rootRef: this.rootRef,
            getLocalState: () => persistence.getLocalState(this.state),
        });

        this.state = useState({
            wizardId: persistence.savedUi.wizardId || null,
            focusAccountId: this.props.action.params?.account_id || null,
            ...persistence.filterState,
            unfoldAll: persistence.savedUi.unfoldAll ?? false,
            lines: [],
            warnings: [],
            currencyId: false,
            dateLabel: "",
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
            accountDetails: persistence.savedUi.detailCache,
            loadingAccounts: {},
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
            lineSearch: "",
            scrollTop: 0,
            viewportHeight: 640,
        });

        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);
        setupReportFilterMenus(this);
        setupLedgerVirtualScroll(this);

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "general.ledger.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                createArgs: [this.props.action.params?.initial_filters || {}],
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "general.ledger.wizard",
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

    getDomain() {
        return [];
    }

    getJournalDomain() {
        return [];
    }

    getAccountDomain() {
        return [];
    }

    get accountFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.accountNames,
            "All Accounts",
            this.state.accountIds
        );
    }

    get visibleLines() {
        return this._flattenLines(this.filterLinesBySearch(this.state.lines));
    }

    get windowedLines() {
        return ledgerWindow(
            this.visibleLines,
            this.state.scrollTop,
            this.state.viewportHeight
        ).lines;
    }

    get windowPad() {
        const pad = ledgerWindow(
            this.visibleLines,
            this.state.scrollTop,
            this.state.viewportHeight
        );
        return { top: pad.top, bottom: pad.bottom };
    }

    get virtualColspan() {
        let count = 4;
        for (const column of OPTIONAL_COLUMNS) {
            if (this.isColumnVisible(column.id)) {
                count += 1;
            }
        }
        return count;
    }

    _loadFilters(filters) {
        if (this._restoringUiState) {
            return;
        }
        this.state.dateFrom = filters.date_from || "";
        this.state.dateTo = filters.date_to || "";
        this.state.targetMove = filters.target_move || "posted";
        this.state.journalIds = filters.journal_ids || [];
        this.state.journalNames = filters.journal_names || [];
        this.state.accountIds = filters.account_ids || [];
        this.state.accountNames = filters.account_names || [];
        this.state.analyticAccountId = filters.analytic_account_id || false;
        this.state.analyticAccountName = filters.analytic_account_name || "";
        if (!this._restoringUiState) {
            this.state.unfoldAll = !!filters.unfold_all;
        }
    }

    _filterPayload() {
        const payload = {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            target_move: this.state.targetMove,
            journal_ids: this.state.journalIds,
            account_ids: this.state.accountIds,
            analytic_account_id: this.state.analyticAccountId || false,
            unfold_all: this.state.unfoldAll,
        };
        if (this.state.focusAccountId) {
            payload.account_ids = [this.state.focusAccountId];
            payload.unfold_all = true;
        }
        return payload;
    }

    _getAccountChildren(line) {
        if (this.state.unfoldAll && line.children?.length) {
            return line.children;
        }
        if (line.account_id && this.state.accountDetails[line.account_id]) {
            return this.state.accountDetails[line.account_id];
        }
        return line.children || [];
    }

    _flattenLines(lines) {
        const result = [];

        const isExpanded = (line) => {
            if (!line.foldable) {
                return false;
            }
            if (line.id in this.state.expandedIds) {
                return this.state.expandedIds[line.id];
            }
            return this.state.unfoldAll;
        };

        const walk = (line) => {
            result.push(line);
            if (!line.foldable) {
                return;
            }
            if (!isExpanded(line)) {
                return;
            }
            const children = this._getAccountChildren(line);
            for (const child of children) {
                walk(child);
            }
        };

        for (const line of lines) {
            walk(line);
        }
        return result;
    }

    async refreshReport(options = {}) {
        this._reportPersistence?.persistFilters(this.state);
        const preserveUi = options.preserveUiState;
        const savedExpanded = preserveUi ? { ...this.state.expandedIds } : {};
        const savedDetails = preserveUi ? { ...this.state.accountDetails } : {};

        this.state.loading = true;
        if (!preserveUi) {
            this.state.accountDetails = {};
        }
        await writeAndSyncFilters(
            this.orm,
            "general.ledger.wizard",
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(
            "general.ledger.wizard",
            "get_report_lines",
            [this.state.wizardId]
        );
        this.state.lines = data.lines || [];
        this.state.warnings = data.warnings || [];
        this.state.currencyId = data.currency_id;
        this.state.dateLabel = data.date_label || this.state.dateTo;
        this.state.loading = false;

        if (preserveUi) {
            this.state.expandedIds = savedExpanded;
            this.state.accountDetails = savedDetails;
        }
        this._cacheAccountChildrenFromLines();

        if (this.state.focusAccountId) {
            const accountLine = this.state.lines.find(
                (line) => line.account_id === this.state.focusAccountId
            );
            if (accountLine) {
                this.state.expandedIds = {
                    ...this.state.expandedIds,
                    [accountLine.id]: true,
                };
                if (!this.state.accountDetails[this.state.focusAccountId]) {
                    await this._loadAccountDetail(this.state.focusAccountId);
                }
            }
        } else if (preserveUi && !this.state.unfoldAll) {
            await this._ensureExpandedAccountDetails();
        }
    }

    _cacheAccountChildrenFromLines() {
        const details = { ...this.state.accountDetails };
        for (const line of this.state.lines) {
            if (line.account_id && line.children?.length) {
                details[line.account_id] = line.children;
            }
        }
        this.state.accountDetails = details;
    }

    _hasCachedUnfoldedChildren() {
        const foldable = this.state.lines.filter(
            (line) => line.line_type === "account" && line.foldable
        );
        if (!foldable.length) {
            return false;
        }
        return foldable.every((line) => {
            const children = line.children?.length
                ? line.children
                : this.state.accountDetails[line.account_id];
            return Boolean(children?.length);
        });
    }

    applyUnfoldAll() {
        if (!this.state.unfoldAll) {
            return;
        }
        if (this._hasCachedUnfoldedChildren()) {
            return;
        }
        this.refreshReport();
    }

    async _loadAccountDetail(accountId) {
        const result = await this.orm.call(
            "general.ledger.wizard",
            "get_account_detail",
            [this.state.wizardId, accountId]
        );
        this.state.accountDetails = {
            ...this.state.accountDetails,
            [accountId]: result.children || [],
        };
    }

    async _ensureExpandedAccountDetails() {
        if (this.state.unfoldAll) {
            return;
        }
        const jobs = [];
        for (const line of this.state.lines) {
            if (
                line.account_id &&
                this.isExpanded(line) &&
                !this.state.accountDetails[line.account_id]
            ) {
                jobs.push(this._loadAccountDetail(line.account_id));
            }
        }
        if (jobs.length) {
            await Promise.all(jobs);
        }
    }

    formatAmount(amount) {
        if (amount === false || amount === null || amount === undefined) {
            return "";
        }
        if (!this.state.currencyId) {
            return Number(amount).toFixed(2);
        }
        return formatMonetary(amount, { currencyId: this.state.currencyId });
    }

    formatCurrencyAmount(line) {
        if (!line.amount_currency || !line.currency_name) {
            return "";
        }
        return `${Number(line.amount_currency).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })} ${line.currency_name}`;
    }

    amountClass(amount) {
        if (amount < 0) {
            return "ages-bs-amount-negative";
        }
        if (amount === 0) {
            return "ages-bs-amount-zero";
        }
        return "";
    }

    rowClass(line) {
        let cls = "";
        if (line.line_type === "total") {
            cls = "o_ages_bs_row-total";
        } else if (line.line_type === "account") {
            cls = "o_ages_bs_row-account";
        } else if (line.line_type === "initial") {
            cls = "o_ages_gl_row-initial";
        } else if (line.line_type === "move_line") {
            cls = "o_ages_gl_row-detail";
        }
        if (line.foldable && this.isExpanded(line)) {
            cls += " o_ages_row-unfolded";
        }
        return cls;
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
        this.state.expandedIds = { ...this.state.expandedIds, [line.id]: next };

        if (next && line.account_id && !this.state.accountDetails[line.account_id]) {
            this.state.loadingAccounts = {
                ...this.state.loadingAccounts,
                [line.account_id]: true,
            };
            await this._loadAccountDetail(line.account_id);
            this.state.loadingAccounts = {
                ...this.state.loadingAccounts,
                [line.account_id]: false,
            };
        }
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.debouncedRefresh();
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.debouncedRefresh();
    }

    onTargetMoveChange(ev) {
        this.state.targetMove = ev.target.value;
        this.debouncedRefresh();
    }

    onUnfoldAllChange(ev) {
        this.state.unfoldAll = ev.target.checked;
        this.state.expandedIds = {};
        this.applyUnfoldAll();
    }

    _runAction(action) {
        if (action?.type) {
            this.actionService.doAction(action);
        }
    }

    async onPrintPdf() {
        await this.refreshReport();
        const action = await this.orm.call(
            "general.ledger.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(
            "general.ledger.wizard",
            "action_print_excel",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    openJournalItems(line) {
        if (!line.account_id) {
            return;
        }
        this._runAction(buildJournalItemsForAccountAction({
            accountId: line.account_id,
            accountName: line.name,
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            targetMove: this.state.targetMove,
        }));
    }

    openJournalEntry(line) {
        const moveId = line.move_id;
        if (!moveId) {
            return;
        }
        this._runAction(buildJournalEntryAction(moveId, line.name, {
            moveLineId: line.move_line_id,
        }));
    }

    openMoveJournalItems(line) {
        if (!line.move_id) {
            return;
        }
        this._runAction(buildMoveLineListAction({
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

    isAccountLoading(line) {
        return line.account_id && this.state.loadingAccounts[line.account_id];
    }

    get optionalColumnDefs() {
        return OPTIONAL_COLUMNS;
    }
}

applyReportFilterMenus(AgesGeneralLedgerReport);
applyReportOptionalColumns(AgesGeneralLedgerReport);

registry.category("actions").add("ages_general_ledger_report", AgesGeneralLedgerReport);
