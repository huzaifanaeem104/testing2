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
    buildJournalItemsForPartnerAction,
    buildMoveLineListAction,
    buildPartnerAction,
} from "../report_navigation/report_navigation";
import {
    bootstrapReportWizard,
    setupReportPersistence,
    writeAndSyncFilters,
} from "../report_state_utils/report_state_utils";
import {
    applyReportFilterMenus,
    setupReportFilterMenus,
} from "../report_filters/report_filters";
import { ledgerWindow, setupLedgerVirtualScroll } from "../report_virtual_rows/report_virtual_rows";

const OPTIONAL_COLUMNS = [
    { id: "journal", label: "Journal" },
    { id: "account", label: "Account" },
    { id: "project", label: "Project", defaultVisible: true },
    { id: "invoice_date", label: "Invoice Date" },
    { id: "due_date", label: "Due Date" },
    { id: "matching", label: "Matching" },
    { id: "amount_currency", label: "Amount Currency" },
];
const PERSISTED_FILTERS = [
    "dateFrom", "dateTo", "targetMove", "partnerIds", "partnerNames",
    "accountIds", "accountNames",
    "journalIds", "journalNames",
    "analyticAccountId", "analyticAccountName",
    "filterReceivable", "filterNonTradeReceivable",
    "filterPayable", "filterNonTradePayable",
    "optionalColumns",
];
const FILTER_DEFAULTS = {
    dateFrom: "",
    dateTo: "",
    targetMove: "posted",
    partnerIds: [],
    partnerNames: [],
    accountIds: [],
    accountNames: [],
    journalIds: [],
    journalNames: [],
    analyticAccountId: false,
    analyticAccountName: "",
    filterReceivable: true,
    filterNonTradeReceivable: false,
    filterPayable: true,
    filterNonTradePayable: false,
    optionalColumns: optionalColumnDefaults(OPTIONAL_COLUMNS),
};

export class AgesPartnerLedgerReport extends Component {
    static template = "ages_custom_reports.AgesPartnerLedgerReport";
    static components = { Layout, ReportLineMenu, ReportOptionalColumns };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        const persistence = setupReportPersistence(this.props, {
            filterFields: PERSISTED_FILTERS,
            filterDefaults: FILTER_DEFAULTS,
            detailCacheField: "partnerDetails",
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
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
            lineSearch: "",
            lines: [],
            warnings: [],
            currencyId: false,
            dateLabel: "",
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
            partnerDetails: persistence.savedUi.detailCache,
            loadingPartners: {},
            scrollTop: 0,
            viewportHeight: 640,
        });

        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);
        setupReportFilterMenus(this);
        setupLedgerVirtualScroll(this);

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "partner.ledger.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "partner.ledger.wizard",
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

    getPartnerDomain() {
        return [];
    }

    getAccountDomain() {
        return [];
    }

    get accountFilterLabel() {
        const labels = [];
        if (this.state.filterReceivable || this.state.filterPayable) {
            if (this.state.filterReceivable && this.state.filterPayable) {
                labels.push("Trade Partners");
            } else if (this.state.filterReceivable) {
                labels.push("Receivable");
            } else if (this.state.filterPayable) {
                labels.push("Payable");
            }
        }
        if (this.state.filterNonTradeReceivable) {
            labels.push("Non Trade Receivable");
        }
        if (this.state.filterNonTradePayable) {
            labels.push("Non Trade Payable");
        }
        return labels.length ? `Account: ${labels.join(", ")}` : "Account: All Types";
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
        this.state.partnerIds = filters.partner_ids || [];
        this.state.partnerNames = filters.partner_names || [];
        this.state.accountIds = filters.account_ids || [];
        this.state.accountNames = filters.account_names || [];
        this.state.journalIds = filters.journal_ids || [];
        this.state.journalNames = filters.journal_names || [];
        this.state.analyticAccountId = filters.analytic_account_id || false;
        this.state.analyticAccountName = filters.analytic_account_name || "";
        this.state.filterReceivable = filters.filter_receivable !== false;
        this.state.filterNonTradeReceivable = !!filters.filter_non_trade_receivable;
        this.state.filterPayable = filters.filter_payable !== false;
        this.state.filterNonTradePayable = !!filters.filter_non_trade_payable;
        if (!this._restoringUiState) {
            this.state.unfoldAll = !!filters.unfold_all;
        }
    }

    _filterPayload() {
        return {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            target_move: this.state.targetMove,
            partner_ids: this.state.partnerIds,
            account_ids: this.state.accountIds,
            journal_ids: this.state.journalIds,
            analytic_account_id: this.state.analyticAccountId || false,
            filter_receivable: this.state.filterReceivable,
            filter_non_trade_receivable: this.state.filterNonTradeReceivable,
            filter_payable: this.state.filterPayable,
            filter_non_trade_payable: this.state.filterNonTradePayable,
            unfold_all: this.state.unfoldAll,
        };
    }

    _isCompletePartnerDetail(children) {
        if (!children?.length) {
            return false;
        }
        return children.some(
            (child) => child.line_type === "move_line" || child.line_type === "initial"
        );
    }

    _getPartnerChildren(line) {
        if (this.state.unfoldAll && this._isCompletePartnerDetail(line.children)) {
            return line.children;
        }
        const key = line.partner_id || "none";
        const cached = this.state.partnerDetails[key];
        if (this._isCompletePartnerDetail(cached)) {
            return cached;
        }
        if (this.state.unfoldAll && line.children?.length) {
            return line.children;
        }
        // An empty fetch must not hide OPAL rows already on the partner line.
        if (Array.isArray(cached) && cached.length) {
            return cached;
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
            for (const child of this._getPartnerChildren(line)) {
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
        const savedDetails = preserveUi ? { ...this.state.partnerDetails } : {};

        this.state.loading = true;
        if (!preserveUi) {
            this.state.partnerDetails = {};
        }
        await writeAndSyncFilters(
            this.orm,
            "partner.ledger.wizard",
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(
            "partner.ledger.wizard",
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
            this.state.partnerDetails = savedDetails;
        }
        this._cachePartnerChildrenFromLines();
        if (!this.state.unfoldAll) {
            await this._ensureExpandedPartnerDetails();
        }
    }

    _partnerKey(line) {
        return line.partner_id || "none";
    }

    _cachePartnerChildrenFromLines() {
        const details = { ...this.state.partnerDetails };
        for (const line of this.state.lines) {
            if (
                line.line_type === "partner"
                && this._isCompletePartnerDetail(line.children)
            ) {
                details[this._partnerKey(line)] = line.children;
            }
        }
        this.state.partnerDetails = details;
    }

    _hasCachedUnfoldedChildren() {
        const foldable = this.state.lines.filter(
            (line) => line.line_type === "partner" && line.foldable
        );
        if (!foldable.length) {
            return false;
        }
        return foldable.every((line) => {
            const children = this._isCompletePartnerDetail(line.children)
                ? line.children
                : this.state.partnerDetails[this._partnerKey(line)];
            return this._isCompletePartnerDetail(children);
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

    async _loadPartnerDetail(partnerId) {
        const key = partnerId || "none";
        const result = await this.orm.call(
            "partner.ledger.wizard",
            "get_partner_detail",
            [this.state.wizardId, partnerId || false]
        );
        const children = result.children || [];
        const current = this.state.lines.find(
            (line) => line.line_type === "partner" && this._partnerKey(line) === key
        );
        this.state.partnerDetails = {
            ...this.state.partnerDetails,
            [key]: this._isCompletePartnerDetail(children) || children.length
                ? children
                : (current?.children || children),
        };
    }

    async _ensureExpandedPartnerDetails() {
        if (this.state.unfoldAll) {
            return;
        }
        const jobs = [];
        for (const line of this.state.lines) {
            if (line.line_type !== "partner" || !this.isExpanded(line)) {
                continue;
            }
            const cached = this.state.partnerDetails[this._partnerKey(line)];
            if (!this._isCompletePartnerDetail(cached)) {
                jobs.push(this._loadPartnerDetail(line.partner_id));
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
        } else if (line.line_type === "partner") {
            cls = "o_ages_pl_row-partner";
        } else if (line.line_type === "initial") {
            cls = "o_ages_pl_row-initial";
        } else if (line.line_type === "move_line") {
            cls = "o_ages_pl_row-detail";
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

        if (next && line.line_type === "partner") {
            const key = this._partnerKey(line);
            if (!this._isCompletePartnerDetail(this.state.partnerDetails[key])) {
                this.state.loadingPartners = { ...this.state.loadingPartners, [key]: true };
                await this._loadPartnerDetail(line.partner_id);
                this.state.loadingPartners = { ...this.state.loadingPartners, [key]: false };
            }
        }
    }

    isPartnerLoading(line) {
        const key = line.partner_id || "none";
        return line.line_type === "partner" && this.state.loadingPartners[key];
    }

    onAccountFilterChange(filterKey, ev) {
        this.state[filterKey] = ev.target.checked;
        this.debouncedRefresh();
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
            "partner.ledger.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(
            "partner.ledger.wizard",
            "action_print_excel",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    openPartner(line) {
        const partnerId = line.partner_id || false;
        if (!partnerId) {
            return;
        }
        this._runAction(buildPartnerAction(partnerId, line.name));
    }

    openJournalItems(line) {
        this._runAction(buildJournalItemsForPartnerAction({
            partnerId: line.partner_id || false,
            partnerName: line.name,
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            targetMove: this.state.targetMove,
            analyticAccountId: this.state.analyticAccountId || false,
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

    get optionalColumnDefs() {
        return OPTIONAL_COLUMNS;
    }

    get amountColspan() {
        return 3 + (this.isColumnVisible("amount_currency") ? 1 : 0);
    }
}

applyReportFilterMenus(AgesPartnerLedgerReport);
applyReportOptionalColumns(AgesPartnerLedgerReport);

registry.category("actions").add("ages_partner_ledger_report", AgesPartnerLedgerReport);
