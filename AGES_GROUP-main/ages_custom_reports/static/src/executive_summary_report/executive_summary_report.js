/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { formatMonetary } from "@web/views/fields/formatters";
import {
    bootstrapReportWizard,
    setupReportPersistence,
    writeAndSyncFilters,
} from "../report_state_utils/report_state_utils";
import {
    applyReportFilterMenus,
    setupReportFilterMenus,
} from "../report_filters/report_filters";

const PERSISTED_FILTERS = ["dateFrom", "dateTo", "targetMove"];
const FILTER_DEFAULTS = {
    dateFrom: "",
    dateTo: "",
    targetMove: "posted",
};

export class AgesExecutiveSummaryReport extends Component {
    static template = "ages_custom_reports.AgesExecutiveSummaryReport";
    static components = { Layout };
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
            expandedIds: persistence.savedUi.expandedIds,
            lineSearch: "",
            lines: [],
            warnings: [],
            currencyId: false,
            dateLabel: "",
            loading: false,
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
        });

        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);
        setupReportFilterMenus(this);

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "executive.summary.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "executive.summary.wizard",
                        "get_filter_values",
                        [this.state.wizardId]
                    );
                    this._loadFilters(filters);
                },
                state: this.state,
                persistFilters: (state) => this._reportPersistence?.persistFilters(state),
            });
            await this.refreshReport();
            this._restoringUiState = false;
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get visibleLines() {
        const result = [];
        const isExpanded = (line) => {
            if (!line.foldable) {
                return true;
            }
            if (line.id in this.state.expandedIds) {
                return this.state.expandedIds[line.id];
            }
            return this.state.unfoldAll;
        };
        for (const section of this.filterLinesBySearch(this.state.lines)) {
            result.push(section);
            if (!isExpanded(section)) {
                continue;
            }
            for (const child of section.children || []) {
                result.push(child);
            }
        }
        return result;
    }

    _loadFilters(filters) {
        if (this._restoringUiState) {
            return;
        }
        this.state.dateFrom = filters.date_from || "";
        this.state.dateTo = filters.date_to || "";
        this.state.targetMove = filters.target_move || "posted";
    }

    _filterPayload() {
        return {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            target_move: this.state.targetMove,
        };
    }

    async refreshReport() {
        this._reportPersistence?.persistFilters(this.state);
        this.state.loading = true;
        await writeAndSyncFilters(
            this.orm,
            "executive.summary.wizard",
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(
            "executive.summary.wizard",
            "get_report_lines",
            [this.state.wizardId]
        );
        this.state.lines = data.lines || [];
        this.state.warnings = data.warnings || [];
        this.state.currencyId = data.currency_id;
        this.state.dateLabel = data.date_label || this.state.dateTo;
        this.state.loading = false;
    }

    formatValue(line) {
        const value = line.balance;
        if (line.figure_type === "percentage") {
            return `${Number(value).toFixed(1)}%`;
        }
        if (line.figure_type === "float") {
            return Number(value).toFixed(1);
        }
        if (!this.state.currencyId) {
            return Number(value).toFixed(2);
        }
        return formatMonetary(value, { currencyId: this.state.currencyId });
    }

    amountClass(line) {
        if (line.line_type === "section") {
            return "";
        }
        if (line.balance < 0) {
            return "ages-bs-amount-negative";
        }
        if (line.balance === 0) {
            return "ages-bs-amount-zero";
        }
        return "";
    }

    rowClass(line) {
        if (line.line_type === "section") {
            return "o_ages_bs_row-section";
        }
        return "o_ages_bs_row-account";
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

    async _runAction(action) {
        if (action && action.type) {
            await this.actionService.doAction(action);
        }
    }

    async onPrintPdf() {
        await this.refreshReport();
        const action = await this.orm.call(
            "executive.summary.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(
            "executive.summary.wizard",
            "action_print_excel",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }
}

applyReportFilterMenus(AgesExecutiveSummaryReport);

registry.category("actions").add("ages_executive_summary_report", AgesExecutiveSummaryReport);
