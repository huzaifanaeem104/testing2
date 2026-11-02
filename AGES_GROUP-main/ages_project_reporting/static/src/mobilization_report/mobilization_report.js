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
    buildJournalEntryAction,
    buildPartnerAction,
} from "@ages_custom_reports/report_navigation/report_navigation";
import {
    bootstrapReportWizard,
    setupReportPersistence,
    writeAndSyncFilters,
} from "@ages_custom_reports/report_state_utils/report_state_utils";
import {
    applyReportFilterMenus,
    setupReportFilterMenus,
    selectedRecordsFilterLabel,
} from "@ages_custom_reports/report_filters/report_filters";

const WIZARD_MODEL = "mobilization.report.wizard";

const PERSISTED_FILTERS = [
    "dateFrom",
    "dateTo",
    "partnerIds",
    "partnerNames",
    "projectIds",
    "projectNames",
    "contractIds",
    "contractNames",
    "subCompanyIds",
    "subCompanyNames",
    "contractState",
    "confirmedOnly",
    "showZeroLines",
    "hideTaxEntries",
];
const FILTER_DEFAULTS = {
    dateFrom: "",
    dateTo: "",
    partnerIds: [],
    partnerNames: [],
    projectIds: [],
    projectNames: [],
    contractIds: [],
    contractNames: [],
    subCompanyIds: [],
    subCompanyNames: [],
    contractState: "all",
    confirmedOnly: true,
    showZeroLines: false,
    hideTaxEntries: false,
};

export class AgesMobilizationReport extends Component {
    static template = "ages_project_reporting.AgesMobilizationReport";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        const persistence = setupReportPersistence(this.props, {
            filterFields: PERSISTED_FILTERS,
            filterDefaults: FILTER_DEFAULTS,
            detailCacheField: "clientDetails",
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
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
            clientDetails: persistence.savedUi.detailCache,
            loadingClients: {},
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
                model: WIZARD_MODEL,
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        WIZARD_MODEL,
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

    get visibleLines() {
        return this._flattenLines(this.filterLinesBySearch(this.state.lines));
    }

    get clientFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.partnerNames,
            "All Clients",
            this.state.partnerIds
        );
    }

    get projectFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.projectNames,
            "All Projects",
            this.state.projectIds
        );
    }

    get contractFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.contractNames,
            "All Contracts",
            this.state.contractIds
        );
    }

    get subCompanyFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.subCompanyNames,
            "All Companies",
            this.state.subCompanyIds
        );
    }

    get contractStateLabel() {
        const labels = {
            all: "All States",
            new: "New",
            running: "Running",
            closed: "Closed",
            cancelled: "Cancelled",
        };
        return labels[this.state.contractState] || "All States";
    }

    emptyDomain() {
        return [];
    }

    getPartnerDomain() {
        return [["parent_id", "=", false]];
    }

    getContractDomain() {
        if (!this.state.projectIds?.length) {
            return [];
        }
        return [["project_id", "in", this.state.projectIds]];
    }

    _loadFilters(filters) {
        if (this._restoringUiState) {
            return;
        }
        this.state.dateFrom = filters.date_from || "";
        this.state.dateTo = filters.date_to || "";
        this.state.partnerIds = filters.partner_ids || [];
        this.state.partnerNames = filters.partner_names || [];
        this.state.projectIds = filters.project_ids || [];
        this.state.projectNames = filters.project_names || [];
        this.state.contractIds = filters.contract_ids || [];
        this.state.contractNames = filters.contract_names || [];
        this.state.subCompanyIds = filters.sub_company_ids || [];
        this.state.subCompanyNames = filters.sub_company_names || [];
        this.state.contractState = filters.contract_state || "all";
        this.state.confirmedOnly = filters.confirmed_only !== false;
        this.state.showZeroLines = !!filters.show_zero_lines;
        this.state.hideTaxEntries = !!filters.hide_tax_entries;
        if (!this._restoringUiState) {
            this.state.unfoldAll = !!filters.unfold_all;
        }
    }

    _filterPayload() {
        return {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            partner_ids: this.state.partnerIds,
            project_ids: this.state.projectIds,
            contract_ids: this.state.contractIds,
            sub_company_ids: this.state.subCompanyIds,
            contract_state: this.state.contractState,
            confirmed_only: this.state.confirmedOnly,
            show_zero_lines: this.state.showZeroLines,
            hide_tax_entries: this.state.hideTaxEntries,
            unfold_all: this.state.unfoldAll,
        };
    }

    _clientKey(line) {
        return line.partner_id || "none";
    }

    _getClientChildren(line) {
        if (this.state.unfoldAll && line.children?.length) {
            return line.children;
        }
        const key = this._clientKey(line);
        if (this.state.clientDetails[key]) {
            return this.state.clientDetails[key];
        }
        return line.children || [];
    }

    _flattenLines(lines) {
        const result = [];
        const walk = (line) => {
            if (this.state.hideTaxEntries && this.isTaxEntry(line)) {
                return;
            }
            result.push(line);
            if (!line.foldable || !this.isExpanded(line)) {
                return;
            }
            const children =
                line.line_type === "client" ? this._getClientChildren(line) : line.children || [];
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
        const savedDetails = preserveUi ? { ...this.state.clientDetails } : {};

        this.state.loading = true;
        if (!preserveUi) {
            this.state.clientDetails = {};
        }
        await writeAndSyncFilters(
            this.orm,
            WIZARD_MODEL,
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(WIZARD_MODEL, "get_report_lines", [this.state.wizardId]);
        this.state.lines = data.lines || [];
        this.state.warnings = data.warnings || [];
        this.state.currencyId = data.currency_id;
        this.state.dateLabel = data.date_label || this.state.dateTo;
        this.state.loading = false;

        if (preserveUi) {
            this.state.expandedIds = savedExpanded;
            this.state.clientDetails = savedDetails;
            await this._ensureExpandedClientDetails();
        } else if (this.state.unfoldAll) {
            for (const line of this.state.lines) {
                if (line.line_type === "client" && line.children?.length) {
                    this.state.clientDetails[this._clientKey(line)] = line.children;
                }
            }
        } else if (this.state.partnerIds.length === 1) {
            await this._expandSingleClient();
        }
    }

    async _expandSingleClient() {
        const clientLine = this.state.lines.find((line) => line.line_type === "client");
        if (!clientLine) {
            return;
        }
        this.state.expandedIds = { ...this.state.expandedIds, [clientLine.id]: true };
        await this._loadClientDetail(clientLine.partner_id);
        const children = this.state.clientDetails[this._clientKey(clientLine)] || [];
        const nextExpanded = { ...this.state.expandedIds };
        for (const child of children) {
            if (child.foldable) {
                nextExpanded[child.id] = true;
            }
        }
        this.state.expandedIds = nextExpanded;
    }

    async _loadClientDetail(partnerId) {
        const key = partnerId || "none";
        const result = await this.orm.call(WIZARD_MODEL, "get_client_detail", [
            this.state.wizardId,
            partnerId || false,
        ]);
        this.state.clientDetails = {
            ...this.state.clientDetails,
            [key]: result.children || [],
        };
    }

    async _ensureExpandedClientDetails() {
        for (const line of this.state.lines) {
            if (
                line.line_type === "client" &&
                this.isExpanded(line) &&
                !this.state.clientDetails[this._clientKey(line)]
            ) {
                await this._loadClientDetail(line.partner_id);
            }
        }
    }

    formatPercent(value) {
        if (value === false || value === null || value === undefined || value === 0) {
            return "";
        }
        return Number(value).toFixed(2);
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
        let cls = `o_ages_mr_row-${line.line_type}`;
        if (line.foldable && this.isExpanded(line)) {
            cls += " o_ages_row-unfolded";
        }
        if (["client", "contract", "move_line"].includes(line.line_type)) {
            cls += " o_ages_report_row";
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
        if (next && line.line_type === "client") {
            const key = this._clientKey(line);
            if (!this.state.clientDetails[key]) {
                this.state.loadingClients = { ...this.state.loadingClients, [key]: true };
                await this._loadClientDetail(line.partner_id);
                this.state.loadingClients = { ...this.state.loadingClients, [key]: false };
            }
        }
    }

    isClientLoading(line) {
        return line.line_type === "client" && this.state.loadingClients[this._clientKey(line)];
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.debouncedRefresh();
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.debouncedRefresh();
    }

    async _restrictContractsToProjects() {
        if (!this.state.contractIds.length || !this.state.projectIds.length) {
            return;
        }
        const matchingIds = await this.orm.search("ages.contract", [
            ["id", "in", this.state.contractIds],
            ["project_id", "in", this.state.projectIds],
        ]);
        if (matchingIds.length === this.state.contractIds.length) {
            return;
        }
        const keep = new Set(matchingIds);
        const nextIds = [];
        const nextNames = [];
        this.state.contractIds.forEach((id, index) => {
            if (keep.has(id)) {
                nextIds.push(id);
                nextNames.push(this.state.contractNames[index] || "");
            }
        });
        this.state.contractIds = nextIds;
        this.state.contractNames = nextNames;
    }

    setContractState(value) {
        this.state.contractState = value;
        this.state.openMenu = null;
        this.debouncedRefresh();
    }

    toggleConfirmedOnly() {
        this.state.confirmedOnly = !this.state.confirmedOnly;
        this.state.openMenu = null;
        this.debouncedRefresh();
    }

    toggleShowZeroLines() {
        this.state.showZeroLines = !this.state.showZeroLines;
        this.state.openMenu = null;
        this.debouncedRefresh();
    }

    isTaxEntry(line) {
        if (line.is_tax_entry) {
            return true;
        }
        const haystack = `${line.name || ""} ${line.account_name || ""}`.toUpperCase();
        return (
            haystack.includes("WTH TAX") ||
            haystack.includes("WH TAX") ||
            haystack.includes("WHT TAX") ||
            haystack.includes("WITHHOLDING TAX")
        );
    }

    onHideTaxEntriesChange(ev) {
        this.state.hideTaxEntries = ev.target.checked;
        this._persistHideTaxEntries();
    }

    toggleHideTaxEntries() {
        this.state.hideTaxEntries = !this.state.hideTaxEntries;
        this.state.openMenu = null;
        this._persistHideTaxEntries();
    }

    _persistHideTaxEntries() {
        this._reportPersistence?.persistFilters(this.state);
        if (!this.state.wizardId) {
            return;
        }
        writeAndSyncFilters(
            this.orm,
            WIZARD_MODEL,
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
    }

    toggleUnfoldAll() {
        this.state.unfoldAll = !this.state.unfoldAll;
        this.state.expandedIds = {};
        this.state.openMenu = null;
        this.refreshReport();
    }

    _runAction(action) {
        if (action?.type) {
            this.actionService.doAction(action);
        }
    }

    async onPrintPdf() {
        await this.refreshReport();
        const action = await this.orm.call(WIZARD_MODEL, "action_print_pdf", [
            [this.state.wizardId],
        ]);
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(WIZARD_MODEL, "action_print_excel", [
            [this.state.wizardId],
        ]);
        await this._runAction(action);
    }

    openPartner(line) {
        if (!line.partner_id) {
            return;
        }
        this._runAction(buildPartnerAction(line.partner_id, line.name));
    }

    async openContract(line) {
        if (!line.contract_id) {
            return;
        }
        const action = await this.orm.call(WIZARD_MODEL, "action_open_contract", [
            [this.state.wizardId],
            line.contract_id,
        ]);
        this._runAction(action);
    }

    openJournalEntry(line) {
        if (!line.move_id) {
            return;
        }
        this._runAction(buildJournalEntryAction(line.move_id, line.name));
    }

    onLineNameClick(line) {
        if (line.line_type === "client") {
            this.openPartner(line);
        } else if (line.line_type === "contract") {
            this.openContract(line);
        } else if (line.line_type === "move_line") {
            this.openJournalEntry(line);
        }
    }
}

applyReportFilterMenus(AgesMobilizationReport);

registry.category("actions").add("ages_mobilization_report", AgesMobilizationReport);
