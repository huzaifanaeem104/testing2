/** @odoo-module **/

import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { getCurrency } from "@web/core/currency";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { clipProjectName } from "../report_display/report_display";
import { cloneFilterValue } from "../report_state_utils/report_state_utils";

const IGNORE_SELECTOR = [
    ".o_ages_report_dropdown",
    ".o_ages_apb_dropdown",
    ".o-autocomplete",
    ".o-autocomplete--dropdown-menu",
    ".o_input_dropdown",
    ".o-overlay-item",
    ".o-dropdown--menu",
    ".o_multi_record_selector",
    ".o_record_selector",
    ".o_tag",
    ".o_ages_report_filters .btn",
    ".o_ages_apb_filters .btn",
    ".o_ages_optional_columns",
].join(", ");

export class ReportRecordPicker extends Component {
    static template = "ages_custom_reports.ReportRecordPicker";
    static components = { MultiRecordSelector };
    static props = {
        resIds: { type: Array, optional: true },
        resModel: String,
        update: Function,
        domain: { type: Array, optional: true },
        placeholder: { type: String, optional: true },
        fieldString: { type: String, optional: true },
        single: { type: Boolean, optional: true },
    };
    static defaultProps = {
        placeholder: "Search...",
        fieldString: "Records",
        single: false,
    };

    get domain() {
        return this.props.domain || [];
    }

    get selectedIds() {
        return (this.props.resIds || []).filter((id) => Number.isInteger(id) && id > 0);
    }

    onUpdate(resIds) {
        const ids = this.props.single ? (resIds || []).slice(-1) : (resIds || []);
        this.props.update(ids);
    }
}

export function formatFilterDate(isoDate) {
    if (!isoDate) {
        return "";
    }
    const [year, month, day] = String(isoDate).split("-");
    if (!year || !month || !day) {
        return isoDate;
    }
    return `${month}/${day}/${year}`;
}

export function asOfFilterLabel(isoDate) {
    const formatted = formatFilterDate(isoDate);
    return formatted ? `As of ${formatted}` : "As of";
}

export function dateRangeFilterLabel(dateFrom, dateTo) {
    const from = formatFilterDate(dateFrom);
    const to = formatFilterDate(dateTo);
    if (from && to) {
        return `${from} — ${to}`;
    }
    return from || to || "Date";
}

export function namesFromRecords(records) {
    return records ? records.map((r) => r.display_name || r.name || "").filter(Boolean) : [];
}

export function selectedRecordsFilterLabel(names, emptyLabel, ids = []) {
    const list = (names || []).map((name) => String(name || "").trim()).filter(Boolean);
    const count = list.length || (ids || []).length;
    if (!count) {
        return emptyLabel;
    }
    if (list.length === 1) {
        return list[0];
    }
    if (list.length === 2) {
        return `${list[0]}, ${list[1]}`;
    }
    if (list.length > 2) {
        return `${list[0]} +${list.length - 1}`;
    }
    return `${count} selected`;
}

export function targetMoveFilterLabel(targetMove) {
    if (targetMove === "all") {
        return "All Entries";
    }
    if (targetMove === "draft") {
        return "Draft Entries";
    }
    return "Posted Entries";
}

export function setupReportFilterMenus(component) {
    const onDocumentClick = (ev) => {
        if (!component.state.openMenu) {
            return;
        }
        if (ev.target.closest(IGNORE_SELECTOR)) {
            return;
        }
        component.state.openMenu = null;
    };
    const onDocumentKeydown = (ev) => {
        if (ev.key !== "Escape" || !component.state.openMenu) {
            return;
        }
        component.state.openMenu = null;
    };
    onMounted(() => {
        document.addEventListener("click", onDocumentClick, true);
        document.addEventListener("keydown", onDocumentKeydown, true);
    });
    onWillUnmount(() => {
        document.removeEventListener("click", onDocumentClick, true);
        document.removeEventListener("keydown", onDocumentKeydown, true);
    });
}

function asIntegerIds(resIds) {
    return [...new Set((resIds || []).filter((id) => Number.isInteger(id) && id > 0))];
}

export const ReportFilterMenus = {
    toggleFilterMenu(menuName, ev) {
        ev.stopPropagation();
        const next = this.state.openMenu === menuName ? null : menuName;
        this.state.openMenu = next;
        if (next) {
            const rect = ev.currentTarget.getBoundingClientRect();
            this.state.menuTop = rect.bottom + 6;
            this.state.menuLeft = rect.left;
        }
    },

    filterMenuStyle() {
        const width = 360;
        let left = this.state.menuLeft || 8;
        const top = this.state.menuTop || 0;
        if (typeof window !== "undefined") {
            left = Math.min(left, window.innerWidth - width - 8);
            left = Math.max(8, left);
        }
        return `top: ${top}px; left: ${left}px;`;
    },

    get asOfFilterLabel() {
        return asOfFilterLabel(this.state.dateTo);
    },

    get dateRangeFilterLabel() {
        return dateRangeFilterLabel(this.state.dateFrom, this.state.dateTo);
    },

    get targetMoveFilterLabel() {
        return targetMoveFilterLabel(this.state.targetMove);
    },

    get analyticFilterLabel() {
        return clipProjectName(this.state.analyticAccountName) || "All Projects";
    },

    get projectFilterLabel() {
        return selectedRecordsFilterLabel(
            (this.state.projectNames || []).map(clipProjectName),
            clipProjectName(this.state.analyticAccountName) || "All Projects",
            this.state.projectIds
        );
    },

    get partnerFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.partnerNames,
            this.state.partnerName || "All Partners",
            this.state.partnerIds
        );
    },

    get journalFilterLabel() {
        return selectedRecordsFilterLabel(
            this.state.journalNames,
            "All Journals",
            this.state.journalIds
        );
    },

    get accountSearchLabel() {
        return selectedRecordsFilterLabel(
            this.state.accountNames,
            this.state.accountName || "All Accounts",
            this.state.accountIds
        );
    },

    get currencyFilterLabel() {
        if (this.state.currencyLabel) {
            return this.state.currencyLabel;
        }
        const symbol = this.state.currencySymbol;
        if (symbol) {
            return `In ${symbol}`;
        }
        if (this.state.currencyId) {
            const currency = getCurrency(this.state.currencyId);
            const mark = currency?.symbol || currency?.name || "";
            return mark ? `In ${mark}` : "";
        }
        return "";
    },

    get analyticResIds() {
        return this.state.analyticAccountId ? [this.state.analyticAccountId] : [];
    },

    get accountOneResIds() {
        return this.state.accountId ? [this.state.accountId] : [];
    },

    get partnerOneResIds() {
        return this.state.partnerId ? [this.state.partnerId] : [];
    },

    get subCompanyOneResIds() {
        return this.state.subCompanyId ? [this.state.subCompanyId] : [];
    },

    get emptyRecordDomain() {
        return [];
    },

    async applyMultiRecordFilter(idsKey, namesKey, resModel, resIds, options = {}) {
        const ids = asIntegerIds(resIds);
        this.state[idsKey] = ids;
        if (!ids.length) {
            this.state[namesKey] = [];
        } else {
            const records = await this.orm.read(resModel, ids, ["display_name"]);
            const nameById = Object.fromEntries(records.map((r) => [r.id, r.display_name || ""]));
            this.state[namesKey] = ids.map((id) => nameById[id] || "");
        }
        if (options.refresh === false) {
            return;
        }
        this.debouncedRefresh();
    },

    async applySingleRecordFilter(idKey, nameKey, resModel, resIds, options = {}) {
        const id = asIntegerIds(resIds).at(-1) || false;
        this.state[idKey] = id;
        if (!id) {
            this.state[nameKey] = "";
        } else {
            const [record] = await this.orm.read(resModel, [id], ["display_name"]);
            this.state[nameKey] = record?.display_name || "";
        }
        if (options.refresh === false) {
            return;
        }
        this.debouncedRefresh();
    },

    onAccountUpdate(resIds) {
        if ("focusAccountId" in this.state) {
            this.state.focusAccountId = null;
        }
        if (Array.isArray(this.state.accountIds)) {
            return this.applyMultiRecordFilter("accountIds", "accountNames", "account.account", resIds);
        }
        return this.applySingleRecordFilter("accountId", "accountName", "account.account", resIds);
    },

    onPartnerUpdate(resIds) {
        if (Array.isArray(this.state.partnerIds)) {
            return this.applyMultiRecordFilter("partnerIds", "partnerNames", "res.partner", resIds);
        }
        return this.applySingleRecordFilter("partnerId", "partnerName", "res.partner", resIds);
    },

    onJournalUpdate(resIds) {
        return this.applyMultiRecordFilter("journalIds", "journalNames", "account.journal", resIds);
    },

    onAnalyticUpdate(resIds) {
        return this.applySingleRecordFilter(
            "analyticAccountId",
            "analyticAccountName",
            "account.analytic.account",
            resIds
        );
    },

    async onSubCompanyUpdate(resIds) {
        if (Array.isArray(this.state.subCompanyIds)) {
            return this.applyMultiRecordFilter(
                "subCompanyIds",
                "subCompanyNames",
                "ages.sub.company",
                resIds
            );
        }
        await this.applySingleRecordFilter(
            "subCompanyId",
            "subCompanyName",
            "ages.sub.company",
            resIds,
            { refresh: false }
        );
        if ("analyticAccountId" in this.state) {
            this.state.analyticAccountId = false;
            this.state.analyticAccountName = "";
        }
        this.debouncedRefresh();
    },

    async onProjectUpdate(resIds) {
        await this.applyMultiRecordFilter(
            "projectIds",
            "projectNames",
            "project.project",
            resIds,
            { refresh: false }
        );
        if (typeof this._restrictContractsToProjects === "function") {
            await this._restrictContractsToProjects();
        }
        this.debouncedRefresh();
    },

    onContractUpdate(resIds) {
        return this.applyMultiRecordFilter("contractIds", "contractNames", "ages.contract", resIds);
    },

    setTargetMove(value) {
        this.state.targetMove = value;
        this.state.openMenu = null;
        this.debouncedRefresh();
    },

    toggleUnfoldAllOption() {
        this.state.unfoldAll = !this.state.unfoldAll;
        this.state.expandedIds = {};
        this.state.openMenu = null;
        if (typeof this.applyUnfoldAll === "function") {
            this.applyUnfoldAll();
            return;
        }
        if (typeof this.refreshReport === "function") {
            this.refreshReport({ preserveUiState: true });
        } else {
            this.debouncedRefresh();
        }
    },

    onLineSearch(ev) {
        this.state.lineSearch = ev.target.value;
        if ("scrollTop" in this.state) {
            this.state.scrollTop = 0;
            if (this.scrollRef?.el) {
                this.scrollRef.el.scrollTop = 0;
            }
        }
    },

    matchesLineSearch(line) {
        const query = (this.state.lineSearch || "").trim().toLowerCase();
        if (!query) {
            return true;
        }
        return String(line.name || "").toLowerCase().includes(query);
    },

    filterLinesBySearch(lines) {
        const query = (this.state.lineSearch || "").trim().toLowerCase();
        if (!query) {
            return lines;
        }
        const keep = (line) => {
            const children = (line.children || []).map(keep).filter(Boolean);
            const selfMatch = String(line.name || "").toLowerCase().includes(query);
            if (selfMatch || children.length) {
                return { ...line, children: selfMatch ? line.children : children };
            }
            return null;
        };
        return (lines || []).map(keep).filter(Boolean);
    },

    /**
     * Reset all persisted filters to defaults (same behavior as Project Directory Ledger Clear).
     */
    async clearFilters() {
        this.state.openMenu = null;
        const defaults = this._reportPersistence?.filterDefaults || {};
        for (const [field, defaultValue] of Object.entries(defaults)) {
            if (!(field in this.state)) {
                continue;
            }
            this.state[field] = cloneFilterValue(defaultValue);
        }
        if ("lineSearch" in this.state) {
            this.state.lineSearch = "";
        }
        if ("expandedIds" in this.state) {
            this.state.expandedIds = {};
        }
        if ("focusAccountId" in this.state) {
            this.state.focusAccountId = null;
        }
        if ("partnerDetails" in this.state) {
            this.state.partnerDetails = {};
        }
        if ("accountDetails" in this.state) {
            this.state.accountDetails = {};
        }
        if ("loadingPartners" in this.state) {
            this.state.loadingPartners = {};
        }
        if ("loadingAccounts" in this.state) {
            this.state.loadingAccounts = {};
        }
        if ("scrollTop" in this.state) {
            this.state.scrollTop = 0;
            if (this.scrollRef?.el) {
                this.scrollRef.el.scrollTop = 0;
            }
        }
        if (typeof this.refreshReport === "function") {
            await this.refreshReport();
        } else if (typeof this.debouncedRefresh === "function") {
            this.debouncedRefresh();
        }
    },
};

export function applyReportFilterMenus(ctor) {
    const descriptors = Object.getOwnPropertyDescriptors(ReportFilterMenus);
    delete descriptors.constructor;
    Object.defineProperties(ctor.prototype, descriptors);
    ctor.components = { ...ctor.components, ReportRecordPicker };
}
