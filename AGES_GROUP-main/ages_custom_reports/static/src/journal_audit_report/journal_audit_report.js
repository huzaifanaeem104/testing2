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
    buildJournalAuditMoveLinesAction,
    buildTaxAuditAction,
    buildTaxGridAuditAction,
} from "../report_navigation/report_navigation";
import {
    applyReportOptionalColumns,
    optionalColumnDefaults,
    ReportOptionalColumns,
} from "../report_optional_columns/report_optional_columns";
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
    { id: "code", label: "Code" },
];
const PERSISTED_FILTERS = ["dateFrom", "dateTo", "targetMove", "journalIds", "journalNames", "optionalColumns"];
const FILTER_DEFAULTS = {
    dateFrom: "",
    dateTo: "",
    targetMove: "posted",
    journalIds: [],
    journalNames: [],
    optionalColumns: optionalColumnDefaults(OPTIONAL_COLUMNS),
};

export class AgesJournalAuditReport extends Component {
    static template = "ages_custom_reports.AgesJournalAuditReport";
    static components = { Layout, ReportOptionalColumns };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        const persistence = setupReportPersistence(this.props, {
            filterFields: PERSISTED_FILTERS,
            filterDefaults: FILTER_DEFAULTS,
            detailCacheField: "journalDetails",
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
            taxSummary: false,
            warnings: [],
            currencyId: false,
            dateLabel: "",
            loading: false,
            expandedIds: persistence.savedUi.expandedIds,
            journalDetails: persistence.savedUi.detailCache,
            loadingJournals: {},
            openMenu: null,
            menuTop: 0,
            menuLeft: 0,
        });

        this.debouncedRefresh = debounce(() => this.refreshReport(), 350);
        setupReportFilterMenus(this);

        onWillStart(async () => {
            const restoring = this._restoringUiState;
            await bootstrapReportWizard(this.orm, {
                model: "journal.audit.wizard",
                restoring,
                getWizardId: () => this.state.wizardId,
                setWizardId: (wizardId) => {
                    this.state.wizardId = wizardId;
                },
                filterPayload: this._filterPayload(),
                loadFiltersFromServer: async () => {
                    const filters = await this.orm.call(
                        "journal.audit.wizard",
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

    getJournalDomain() {
        return [];
    }

    get visibleLines() {
        return this._flattenLines(this.state.lines);
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
        if (!this._restoringUiState) {
            this.state.unfoldAll = !!filters.unfold_all;
        }
    }

    _filterPayload() {
        return {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            target_move: this.state.targetMove,
            journal_ids: this.state.journalIds,
            unfold_all: this.state.unfoldAll,
        };
    }

    _getJournalChildren(line) {
        if (this.state.unfoldAll && line.children?.length) {
            return line.children;
        }
        const key = line.journal_id;
        if (this.state.journalDetails[key]) {
            return this.state.journalDetails[key];
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
            if (!line.foldable || !isExpanded(line)) {
                return;
            }
            for (const child of this._getJournalChildren(line)) {
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
        const savedDetails = preserveUi ? { ...this.state.journalDetails } : {};

        this.state.loading = true;
        if (!preserveUi) {
            this.state.journalDetails = {};
        }
        await writeAndSyncFilters(
            this.orm,
            "journal.audit.wizard",
            this.state.wizardId,
            this._filterPayload(),
            this.state,
            (state) => this._reportPersistence?.persistFilters(state),
        );
        const data = await this.orm.call(
            "journal.audit.wizard",
            "get_report_lines",
            [this.state.wizardId]
        );
        this.state.lines = data.lines || [];
        this.state.taxSummary = data.tax_summary || false;
        this.state.warnings = data.warnings || [];
        this.state.currencyId = data.currency_id;
        this.state.dateLabel = data.date_label || this.state.dateTo;
        this.state.loading = false;

        if (preserveUi) {
            this.state.expandedIds = savedExpanded;
            this.state.journalDetails = savedDetails;
            await this._ensureExpandedJournalDetails();
        } else if (this.state.unfoldAll) {
            for (const line of this.state.lines) {
                if (line.line_type === "journal" && line.children?.length) {
                    this.state.journalDetails[line.journal_id] = line.children;
                }
            }
        }
    }

    async _loadJournalDetail(journalId) {
        const result = await this.orm.call(
            "journal.audit.wizard",
            "get_journal_accounts",
            [this.state.wizardId, journalId]
        );
        this.state.journalDetails = {
            ...this.state.journalDetails,
            [journalId]: result.children || [],
        };
    }

    async _ensureExpandedJournalDetails() {
        for (const line of this.state.lines) {
            if (
                line.line_type === "journal" &&
                this.isExpanded(line) &&
                !this.state.journalDetails[line.journal_id]
            ) {
                await this._loadJournalDetail(line.journal_id);
            }
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
        if (amount === false || amount === null || amount === undefined) {
            return "";
        }
        if (amount < 0) {
            return "ages-bs-amount-negative";
        }
        if (amount === 0) {
            return "ages-bs-amount-zero";
        }
        return "";
    }

    rowClass(line) {
        if (line.line_type === "journal") {
            return "o_ages_ja_row-journal";
        }
        if (line.line_type === "account") {
            return "o_ages_ja_row-account";
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

    async toggleFold(line) {
        if (!line.foldable) {
            return;
        }
        const next = !this.isExpanded(line);
        this.state.expandedIds = { ...this.state.expandedIds, [line.id]: next };

        if (next && line.line_type === "journal") {
            const key = line.journal_id;
            if (!this.state.journalDetails[key]) {
                this.state.loadingJournals = { ...this.state.loadingJournals, [key]: true };
                await this._loadJournalDetail(key);
                this.state.loadingJournals = { ...this.state.loadingJournals, [key]: false };
            }
        }
    }

    isJournalLoading(line) {
        return line.line_type === "journal" && this.state.loadingJournals[line.journal_id];
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
        this.refreshReport();
    }

    _runAction(action) {
        if (action?.type) {
            this.actionService.doAction(action);
        }
    }

    _auditFilters() {
        return {
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            targetMove: this.state.targetMove,
        };
    }

    async onPrintPdf() {
        await this.refreshReport();
        const action = await this.orm.call(
            "journal.audit.wizard",
            "action_print_pdf",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    async onPrintExcel() {
        await this.refreshReport();
        const action = await this.orm.call(
            "journal.audit.wizard",
            "action_print_excel",
            [[this.state.wizardId]]
        );
        await this._runAction(action);
    }

    openJournalAudit(line) {
        if (!line.journal_id) {
            return;
        }
        this._runAction(buildJournalAuditMoveLinesAction({
            name: `Audit: ${line.name}`,
            journalId: line.journal_id,
            ...this._auditFilters(),
        }));
    }

    openAccountLines(line) {
        if (!line.journal_id || !line.account_id) {
            return;
        }
        this._runAction(buildJournalAuditMoveLinesAction({
            name: line.name,
            journalId: line.journal_id,
            accountId: line.account_id,
            ...this._auditFilters(),
        }));
    }

    openTaxAudit(tax) {
        if (!tax.tax_id) {
            return;
        }
        this._runAction(buildTaxAuditAction({
            taxId: tax.tax_id,
            ...this._auditFilters(),
        }));
    }

    openTaxGridAudit(grid) {
        this._runAction(buildTaxGridAuditAction({
            tagIds: grid.tag_ids || [],
            ...this._auditFilters(),
        }));
    }

    get optionalColumnDefs() {
        return OPTIONAL_COLUMNS;
    }
}

applyReportFilterMenus(AgesJournalAuditReport);
applyReportOptionalColumns(AgesJournalAuditReport);

registry.category("actions").add("ages_journal_audit_report", AgesJournalAuditReport);
