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
import { buildGeneralLedgerClientAction } from "../report_navigation/report_navigation";
import {
    bootstrapReportWizard,
    setupReportPersistence,
    writeAndSyncFilters,
} from "../report_state_utils/report_state_utils";
import {
    applyReportFilterMenus,
    setupReportFilterMenus,
} from "../report_filters/report_filters";

const PERSISTED_FILTERS = ["dateTo", "targetMove", "analyticAccountId", "analyticAccountName"];
const FILTER_DEFAULTS = {
    dateTo: "",
    targetMove: "posted",
    analyticAccountId: false,
    analyticAccountName: "",
};

export class AgesBalanceSheetReport extends Component {
    static template = "ages_custom_reports.AgesBalanceSheetReport";
    static components = { Layout, ReportLineMenu };
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
            unfoldAll: persistence.savedUi.unfoldAll ?? true,
            lines: [],
            warnings: [],
            currencyId: false,
            dateLabel: "",
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
        });

        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);
        setupReportFilterMenus(this);

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "balance.sheet.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "balance.sheet.wizard",
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

    get visibleLines() {
        return this._flattenLines(this.state.lines);
    }

    _loadFilters(filters) {
        if (this._restoringUiState) {
            return;
        }
        this.state.dateTo = filters.date_to || "";
        this.state.targetMove = filters.target_move || "posted";
        this.state.analyticAccountId = filters.analytic_account_id || false;
        this.state.analyticAccountName = filters.analytic_account_name || "";
        if (!this._restoringUiState) {
            this.state.unfoldAll = filters.unfold_all !== false;
        }
    }

    _filterPayload() {
        return {
            date_to: this.state.dateTo || false,
            target_move: this.state.targetMove,
            analytic_account_id: this.state.analyticAccountId || false,
            unfold_all: this.state.unfoldAll,
        };
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
            return this.state.unfoldAll || line.line_type === "section";
        };

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
            "balance.sheet.wizard",
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(
            "balance.sheet.wizard",
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
        }
    }

    formatAmount(amount) {
        if (!this.state.currencyId) {
            return amount.toFixed(2);
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
        if (line.line_type === "section") {
            return "o_ages_bs_row-section";
        }
        if (line.line_type === "total") {
            return "o_ages_bs_row-total";
        }
        if (line.line_type === "account") {
            return "o_ages_bs_row-account";
        }
        return "o_ages_bs_row-group";
    }

    isExpanded(line) {
        if (!line.foldable) {
            return false;
        }
        if (line.id in this.state.expandedIds) {
            return this.state.expandedIds[line.id];
        }
        return this.state.unfoldAll || line.line_type === "section";
    }

    toggleFold(line) {
        if (!line.foldable) {
            return;
        }
        const next = !this.isExpanded(line);
        this.state.expandedIds = { ...this.state.expandedIds, [line.id]: next };
    }

    onDateChange(ev) {
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

    _runAction(action) {
        if (action?.type) {
            this.actionService.doAction(action);
        }
    }

    async onPrintPdf() {
        await this.refreshReport();
        const action = await this.orm.call(
            "balance.sheet.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(
            "balance.sheet.wizard",
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
            dateTo: this.state.dateTo,
            targetMove: this.state.targetMove,
            analyticAccountId: this.state.analyticAccountId,
            parentName: "Balance Sheet",
        }));
    }

    getAccountMenuItems(line) {
        if (line.line_type !== "account" || !line.account_id) {
            return [];
        }
        return [{
            label: "General Ledger",
            onClick: () => this.openGeneralLedger(line),
        }];
    }
}

applyReportFilterMenus(AgesBalanceSheetReport);

registry.category("actions").add("ages_balance_sheet_report", AgesBalanceSheetReport);
