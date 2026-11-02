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

const OPTIONAL_COLUMNS = [
    { id: "date", label: "Date" },
    { id: "partner", label: "Partner" },
    { id: "label", label: "Label" },
    { id: "account", label: "Account" },
    { id: "analytic", label: "Analytic" },
];
const PERSISTED_FILTERS = [
    "dateFrom",
    "dateTo",
    "subCompanyId",
    "subCompanyName",
    "analyticAccountId",
    "analyticAccountName",
    "accountId",
    "accountName",
    "partnerId",
    "partnerName",
    "hideAccountPayable",
    "hideCostOfRevenue",
    "hideBank",
    "targetMove",
    "optionalColumns",
];
const FILTER_DEFAULTS = {
    dateFrom: "",
    dateTo: "",
    subCompanyId: false,
    subCompanyName: "",
    analyticAccountId: false,
    analyticAccountName: "",
    accountId: false,
    accountName: "",
    partnerId: false,
    partnerName: "",
    hideAccountPayable: true,
    hideCostOfRevenue: true,
    hideBank: true,
    targetMove: "posted",
    optionalColumns: optionalColumnDefaults(OPTIONAL_COLUMNS),
};

export class ProjectDirectoryLedgerReport extends Component {
    static template = "ages_custom_reports.ProjectDirectoryLedgerReport";
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
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
            lines: [],
            groupBy: "analytic_distribution",
            groupByLabel: "Project / Analytic Account",
            showAnalyticCol: true,
            currencyId: false,
            dateLabel: "",
            filterLabels: [],
            grandTotals: { debit: 0, credit: 0, balance: 0 },
            groupCount: 0,
            lineCount: 0,
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
        });

        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);
        setupReportFilterMenus(this);

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "project.directory.ledger.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "project.directory.ledger.wizard",
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

    getAnalyticDomain() {
        if (this.state.subCompanyId) {
            return [["ages_contract_id.sub_company_id", "=", this.state.subCompanyId]];
        }
        return [];
    }

    get visibleLines() {
        return this._flattenLines(this.state.lines);
    }

    get hideAccountsFilterLabel() {
        const labels = [];
        if (this.state.hideAccountPayable) {
            labels.push("211000");
        }
        if (this.state.hideCostOfRevenue) {
            labels.push("CoR");
        }
        if (this.state.hideBank) {
            labels.push("Bank");
        }
        if (!labels.length) {
            return "Hide Accounts";
        }
        return `Hide: ${labels.join(", ")}`;
    }

    get companyFilterLabel() {
        return this.state.subCompanyName || "All Active Companies";
    }

    get projectFilterLabel() {
        return this.state.analyticAccountName || "All Projects";
    }

    get accountNameFilterLabel() {
        return this.state.accountName || "All Accounts";
    }

    get partnerFilterLabel() {
        return this.state.partnerName || "All Partners";
    }

    onHideAccountFilterChange(filterKey, ev) {
        this.state[filterKey] = ev.target.checked;
        this.debouncedRefresh();
    }

    _loadFilters(filters) {
        if (this._restoringUiState) {
            return;
        }
        this.state.dateFrom = filters.date_from || "";
        this.state.dateTo = filters.date_to || "";
        this.state.subCompanyId = filters.sub_company_id || false;
        this.state.subCompanyName = filters.sub_company_name || "";
        this.state.analyticAccountId = filters.analytic_account_id || false;
        this.state.analyticAccountName = filters.analytic_account_name || "";
        this.state.accountId = filters.account_id || false;
        this.state.accountName = filters.account_name || "";
        this.state.partnerId = filters.partner_id || false;
        this.state.partnerName = filters.partner_name || "";
        this.state.hideAccountPayable = filters.hide_account_payable !== false;
        this.state.hideCostOfRevenue = filters.hide_cost_of_revenue !== false;
        this.state.hideBank = filters.hide_bank !== false;
        this.state.targetMove = filters.target_move || "posted";
    }

    _filterPayload() {
        return {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            sub_company_id: this.state.subCompanyId || false,
            analytic_account_id: this.state.analyticAccountId || false,
            account_id: this.state.accountId || false,
            partner_id: this.state.partnerId || false,
            hide_account_payable: this.state.hideAccountPayable,
            hide_cost_of_revenue: this.state.hideCostOfRevenue,
            hide_bank: this.state.hideBank,
            target_move: this.state.targetMove || "posted",
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
            return this.state.unfoldAll;
        };

        const walk = (line) => {
            result.push(line);
            if (line.line_type === "group" && isExpanded(line)) {
                for (const child of line.children || []) {
                    result.push(child);
                }
                result.push({
                    id: `${line.id}_subtotal`,
                    line_type: "subtotal",
                    name: "Subtotal",
                    debit: line.debit,
                    credit: line.credit,
                    balance: line.balance,
                    parent_group_id: line.id,
                });
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
            "project.directory.ledger.wizard",
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(
            "project.directory.ledger.wizard",
            "get_report_lines",
            [this.state.wizardId]
        );
        this.state.lines = data.lines || [];
        this.state.groupBy = data.group_by || "analytic_distribution";
        this.state.groupByLabel = data.group_by_label || "";
        this.state.showAnalyticCol = data.show_analytic_col !== false;
        this.state.currencyId = data.currency_id;
        this.state.dateLabel = data.date_label || "";
        this.state.filterLabels = data.filter_labels || [];
        this.state.grandTotals = data.grand_totals || { debit: 0, credit: 0, balance: 0 };
        this.state.groupCount = data.group_count || 0;
        this.state.lineCount = data.line_count || 0;
        this.state.loading = false;

        if (preserveUi) {
            this.state.expandedIds = savedExpanded;
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
        } else if (line.line_type === "group") {
            cls = "o_ages_pdl_row-group";
        } else if (line.line_type === "subtotal") {
            cls = "o_ages_pdl_row-subtotal";
        } else if (line.line_type === "move_line") {
            cls = "o_ages_pdl_row-detail";
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
        this.state.targetMove = ev.target.value || "posted";
        this.debouncedRefresh();
    }

    onUnfoldAllChange(ev) {
        this.state.unfoldAll = ev.target.checked;
        this.state.expandedIds = {};
    }

    _runAction(action) {
        if (action?.type) {
            this.actionService.doAction(action);
        }
    }

    async onPrintPdf() {
        await this.refreshReport();
        const action = await this.orm.call(
            "project.directory.ledger.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(
            "project.directory.ledger.wizard",
            "action_print_excel",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    openPartner(line) {
        const partnerId = line.partner_id;
        if (!partnerId) {
            return;
        }
        this._runAction(buildPartnerAction(partnerId, line.partner_name || line.name));
    }

    openJournalEntry(line) {
        if (!line.move_id) {
            return;
        }
        this._runAction(buildJournalEntryAction(line.move_id, line.name, {
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

    openGroupJournalItems(line) {
        const domain = [];
        if (this.state.dateFrom) {
            domain.push(["date", ">=", this.state.dateFrom]);
        }
        if (this.state.dateTo) {
            domain.push(["date", "<=", this.state.dateTo]);
        }
        if (this.state.targetMove === "posted") {
            domain.push(["parent_state", "=", "posted"]);
        } else if (this.state.targetMove === "draft") {
            domain.push(["parent_state", "=", "draft"]);
        }
        if (line.group_by === "partner_id" && line.partner_id) {
            domain.push(["partner_id", "=", line.partner_id]);
        } else if (line.analytic_account_id) {
            domain.push(["analytic_distribution", "in", [line.analytic_account_id]]);
        }
        if (this.state.accountId) {
            domain.push(["account_id", "=", this.state.accountId]);
        }
        this._runAction(buildMoveLineListAction({
            name: `${line.name} — Journal Items`,
            domain,
            highlightMoveLineId: false,
        }));
    }

    openAccountJournalItems(line) {
        if (!line.account_id) {
            return;
        }
        this._runAction(buildJournalItemsForAccountAction({
            accountId: line.account_id,
            accountName: line.account_name || line.account_code,
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            targetMove: this.state.targetMove || "posted",
            highlightMoveLineId: line.move_line_id,
        }));
    }

    getMoveLineMenuItems(line) {
        if (line.line_type !== "move_line" || !line.move_id) {
            return [];
        }
        const items = [{
            label: "View Journal Entry",
            onClick: () => this.openJournalEntry(line),
        }];
        if (line.move_id) {
            items.push({
                label: "Journal Items",
                onClick: () => this.openMoveJournalItems(line),
            });
        }
        if (line.partner_id) {
            items.push({
                label: "View Partner",
                onClick: () => this.openPartner(line),
            });
        }
        return items;
    }

    get colspanBeforeAmounts() {
        let count = 1;
        if (this.isColumnVisible("date")) {
            count += 1;
        }
        if (this.isColumnVisible("partner")) {
            count += 1;
        }
        if (this.isColumnVisible("label")) {
            count += 1;
        }
        if (this.isColumnVisible("account")) {
            count += 1;
        }
        if (this.state.showAnalyticCol && this.isColumnVisible("analytic")) {
            count += 1;
        }
        return count;
    }

    get optionalColumnDefs() {
        if (this.state.showAnalyticCol) {
            return OPTIONAL_COLUMNS;
        }
        return OPTIONAL_COLUMNS.filter((column) => column.id !== "analytic");
    }
}

applyReportFilterMenus(ProjectDirectoryLedgerReport);
applyReportOptionalColumns(ProjectDirectoryLedgerReport);

registry.category("actions").add("project_directory_ledger_report", ProjectDirectoryLedgerReport);
