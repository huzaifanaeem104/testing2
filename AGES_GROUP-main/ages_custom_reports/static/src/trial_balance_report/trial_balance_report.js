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
    buildGeneralLedgerClientAction,
    buildJournalItemsForAccountAction,
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

const OPTIONAL_COLUMNS = [
    { id: "initial_balance", label: "Initial Balance", defaultVisible: true },
];
const PERSISTED_FILTERS = [
    "dateFrom", "dateTo", "targetMove", "journalIds", "journalNames",
    "analyticAccountId", "analyticAccountName", "hierarchy", "hideZeroLines",
    "optionalColumns",
];
const FILTER_DEFAULTS = {
    dateFrom: "",
    dateTo: "",
    targetMove: "posted",
    journalIds: [],
    journalNames: [],
    analyticAccountId: false,
    analyticAccountName: "",
    hierarchy: true,
    hideZeroLines: false,
    optionalColumns: optionalColumnDefaults(OPTIONAL_COLUMNS),
};

export class AgesTrialBalanceReport extends Component {
    static template = "ages_custom_reports.AgesTrialBalanceReport";
    static components = { Layout, ReportLineMenu, ReportOptionalColumns };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
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
            unfoldAll: persistence.savedUi.unfoldAll ?? false,
            lines: [],
            warnings: [],
            currencyId: false,
            dateLabel: "",
            periodLabel: "",
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
            lineSearch: "",
        });

        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);
        setupReportFilterMenus(this);

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "trial.balance.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                createArgs: [this.props.action.params?.initial_filters || {}],
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "trial.balance.wizard",
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

    get visibleLines() {
        return this._flattenLines(this.filterLinesBySearch(this.state.lines));
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
        this.state.analyticAccountId = filters.analytic_account_id || false;
        this.state.analyticAccountName = filters.analytic_account_name || "";
        if (!this._restoringUiState) {
            this.state.unfoldAll = !!filters.unfold_all;
            this.state.hierarchy = filters.hierarchy !== false;
            this.state.hideZeroLines = !!filters.hide_zero_lines;
        }
    }

    _filterPayload() {
        return {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            target_move: this.state.targetMove,
            journal_ids: this.state.journalIds,
            analytic_account_id: this.state.analyticAccountId || false,
            unfold_all: this.state.unfoldAll,
            hierarchy: this.state.hierarchy,
            hide_zero_lines: this.state.hideZeroLines,
        };
    }

    _flattenLines(lines) {
        const result = [];
        const isExpanded = (line) => this.isExpanded(line);

        const walk = (line) => {
            result.push(line);
            const children = line.children || [];
            if (!children.length) {
                return;
            }
            const showChildren = line.foldable ? isExpanded(line) : true;
            if (showChildren) {
                for (const child of children) {
                    walk(child);
                }
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

        this.state.loading = true;
        await writeAndSyncFilters(
            this.orm,
            "trial.balance.wizard",
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(
            "trial.balance.wizard",
            "get_report_lines",
            [this.state.wizardId]
        );
        this.state.lines = data.lines || [];
        this.state.warnings = data.warnings || [];
        this.state.currencyId = data.currency_id;
        this.state.dateLabel = data.date_label || this.state.dateTo;
        this.state.periodLabel = data.period_label || this.state.dateLabel;
        this.state.loading = false;

        if (preserveUi) {
            this.state.expandedIds = savedExpanded;
        }
    }

    formatAmount(amount) {
        if (!this.state.currencyId) {
            return Number(amount).toFixed(2);
        }
        return formatMonetary(amount, { currencyId: this.state.currencyId });
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
        if (line.line_type === "total") {
            return "o_ages_bs_row-total";
        }
        if (line.line_type === "subtotal") {
            return "o_ages_tb_row-subtotal";
        }
        if (line.line_type === "account") {
            return "o_ages_bs_row-account";
        }
        if (line.line_type === "group") {
            return "o_ages_bs_row-group";
        }
        return "";
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

    toggleFold(line) {
        if (!line.foldable) {
            return;
        }
        const next = !this.isExpanded(line);
        this.state.expandedIds = { ...this.state.expandedIds, [line.id]: next };
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
        this.debouncedRefresh();
    }

    toggleHierarchyOption() {
        this.state.hierarchy = !this.state.hierarchy;
        this.state.openMenu = null;
        this.debouncedRefresh();
    }

    onHierarchyChange(ev) {
        this.state.hierarchy = ev.target.checked;
        this.state.expandedIds = {};
        this.debouncedRefresh();
    }

    onHideZeroChange(ev) {
        this.state.hideZeroLines = ev.target.checked;
        this.debouncedRefresh();
    }

    _runAction(action) {
        if (action?.type) {
            this.actionService.doAction(action);
        }
    }

    async onPrintPdf() {
        await this.refreshReport();
        const action = await this.orm.call(
            "trial.balance.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(
            "trial.balance.wizard",
            "action_print_excel",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    openGeneralLedger(line) {
        if (!line.account_id) {
            return;
        }
        this._runAction(buildGeneralLedgerClientAction({
            accountId: line.account_id,
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            targetMove: this.state.targetMove,
            journalIds: this.state.journalIds,
            analyticAccountId: this.state.analyticAccountId,
            parentName: "Trial Balance",
        }));
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

    getAccountMenuItems(line) {
        if (line.line_type !== "account" || !line.account_id) {
            return [];
        }
        return [
            {
                label: "General Ledger",
                onClick: () => this.openGeneralLedger(line),
            },
            {
                label: "Journal Items",
                onClick: () => this.openJournalItems(line),
            },
        ];
    }

    get optionalColumnDefs() {
        return OPTIONAL_COLUMNS;
    }
}

applyReportFilterMenus(AgesTrialBalanceReport);
applyReportOptionalColumns(AgesTrialBalanceReport);

registry.category("actions").add("ages_trial_balance_report", AgesTrialBalanceReport);
