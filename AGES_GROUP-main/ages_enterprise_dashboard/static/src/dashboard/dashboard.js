/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { registry } from "@web/core/registry";
import { AgesEntChart } from "./widgets/chart";

const STORAGE_KEY = "ages_ent_dashboard_key";
const STORAGE_REFRESH = "ages_ent_dashboard_autorefresh";
const STORAGE_COLLAPSED = "ages_ent_dashboard_collapsed";
const STORAGE_NAV_COLLAPSED = "ages_ent_dashboard_nav_rail";
const STORAGE_PAGE_SIZE = "ages_ent_dashboard_page_size";
const STORAGE_PERIOD = "ages_ent_dashboard_period";
const STORAGE_COMPARE = "ages_ent_dashboard_compare";
const STORAGE_UNAVAILABLE = "ages_ent_dashboard_show_unavailable";
const LIVE_DASHBOARDS = new Set(["action_center", "inventory", "attendance", "governance", "system"]);
const PERIOD_KEYS = new Set([
    "today", "yesterday", "week", "month", "last_month", "quarter", "year", "ytd", "previous_year", "custom",
]);
const COMPARE_KEYS = new Set(["previous_period", "previous_year", "none"]);
const NAV_GROUPS = [
    { id: "briefing", label: "Briefing", keys: ["executive", "action_center"] },
    { id: "commercial", label: "Commercial", keys: ["finance", "contracts", "projects", "sales", "partners"] },
    { id: "operations", label: "Operations", keys: ["procurement", "inventory", "expenses"] },
    { id: "people", label: "People", keys: ["hr", "payroll", "attendance"] },
    { id: "control", label: "Control", keys: ["assets", "governance", "quality_data"] },
    { id: "optional", label: "Optional", keys: ["manufacturing", "crm", "construction", "quality", "system"] },
];
const PRIMARY_PERIODS = [
    { key: "month", label: "Month" },
    { key: "quarter", label: "Quarter" },
    { key: "ytd", label: "YTD" },
    { key: "last_month", label: "Last month" },
    { key: "custom", label: "Custom" },
];
const EXEC_PERIODS = [
    { key: "month", label: "Month" },
    { key: "quarter", label: "Quarter" },
    { key: "ytd", label: "YTD" },
];
const SEVERITY_RANK = { danger: 0, warning: 1, info: 2 };
const SEARCH_KINDS = new Set([
    "project", "contract", "partner", "vendor", "employee", "product",
    "account", "analytic_account", "journal", "location",
]);
const MULTI_FILTERS = [
    ["project", "project_ids", "project_id", "projects", "All projects"],
    ["contract", "contract_ids", "contract_id", "contracts", "All contracts"],
    ["partner", "partner_ids", "partner_id", "partners", "All customers"],
    ["vendor", "vendor_ids", "vendor_id", "vendors", "All vendors"],
    ["department", "department_ids", "department_id", "departments", "All departments"],
    ["warehouse", "warehouse_ids", "warehouse_id", "warehouses", "All warehouses"],
    ["employee", "employee_ids", "employee_id", "employees", "All employees"],
    ["product", "product_ids", "product_id", "products", "All products"],
    ["product_category", "product_category_ids", "product_category_id", "product_categories", "All product categories"],
    ["location", "location_ids", "location_id", "locations", "All locations"],
    ["journal", "journal_ids", "journal_id", "journals", "All journals"],
    ["account", "account_ids", "account_id", "accounts", "All accounts"],
    ["analytic_account", "analytic_account_ids", "analytic_account_id", "analytic_accounts", "All analytic accounts"],
    ["salesperson", "salesperson_ids", "salesperson_id", "salespersons", "All salespersons"],
    ["sales_team", "sales_team_ids", "sales_team_id", "sales_teams", "All sales teams"],
    ["requester", "requester_ids", "requester_id", "requesters", "All requesters"],
];
const QUEUE_GROUP_LABELS = {
    cash: "Cash & credit",
    delivery: "Delivery & site",
    people: "People",
    commercial: "Commercial",
};

function emptyFilters() {
    return {
        period: "month",
        compare_period: "previous_period",
        date_from: "",
        date_to: "",
        company_id: false,
        company_ids: [],
        sub_company_ids: [],
        project_id: false,
        project_ids: [],
        contract_id: false,
        contract_ids: [],
        partner_id: false,
        partner_ids: [],
        vendor_id: false,
        vendor_ids: [],
        department_id: false,
        department_ids: [],
        warehouse_id: false,
        warehouse_ids: [],
        employee_id: false,
        employee_ids: [],
        product_id: false,
        product_ids: [],
        product_category_id: false,
        product_category_ids: [],
        location_id: false,
        location_ids: [],
        journal_id: false,
        journal_ids: [],
        account_id: false,
        account_ids: [],
        analytic_account_id: false,
        analytic_account_ids: [],
        salesperson_id: false,
        salesperson_ids: [],
        sales_team_id: false,
        sales_team_ids: [],
        requester_id: false,
        requester_ids: [],
        approval_status: false,
        approval_statuses: [],
        document_status: false,
        document_statuses: [],
        labour_category: false,
        labour_categories: [],
        reporting_currency_id: false,
    };
}

export class AgesEnterpriseDashboard extends Component {
    static template = "ages_enterprise_dashboard.Root";
    static components = { AgesEntChart };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.inspectorRef = useRef("inspector");
        this.state = useState({
            loading: true,
            error: false,
            dashboards: [],
            activeKey: "executive",
            defaultDashboard: "executive",
            payload: { meta: {}, kpis: [], charts: {}, tables: {}, alerts: [], available: true },
            options: {
                companies: [],
                sub_companies: [],
                projects: [],
                contracts: [],
                partners: [],
                vendors: [],
                departments: [],
                warehouses: [],
                employees: [],
                products: [],
                product_categories: [],
                locations: [],
                journals: [],
                accounts: [],
                analytic_accounts: [],
                salespersons: [],
                sales_teams: [],
                requesters: [],
                approval_statuses: [],
                document_statuses: [],
                labour_categories: [],
                currencies: [],
            },
            searchOptions: {},
            searchQuery: {},
            periods: [],
            comparePeriods: [],
            filterCatalog: {},
            navOpen: false,
            navCollapsed: window.localStorage.getItem(STORAGE_NAV_COLLAPSED) === "1",
            moreFilters: false,
            morePeriods: false,
            mobileFiltersOpen: false,
            moreIndicators: false,
            showCleared: false,
            showUnavailable: window.localStorage.getItem(STORAGE_UNAVAILABLE) === "1",
            warnOpen: false,
            openDropdown: false,
            autoRefresh: window.localStorage.getItem(STORAGE_REFRESH) === "1",
            sort: {},
            tablePage: {},
            pageSize: parseInt(window.localStorage.getItem(STORAGE_PAGE_SIZE) || "10", 10),
            collapsed: this.loadCollapsed(),
            selectedKpi: false,
            refreshing: false,
            chartTypes: {},
            focusedKpi: false,
            focusedQueue: false,
            chartSeriesHidden: {},
            chartHighlightLatest: {},
            watchlistExpanded: {},
            kpiHoverKey: false,
            filters: {
                ...emptyFilters(),
                period: PERIOD_KEYS.has(window.localStorage.getItem(STORAGE_PERIOD))
                    ? window.localStorage.getItem(STORAGE_PERIOD)
                    : "month",
                compare_period: COMPARE_KEYS.has(window.localStorage.getItem(STORAGE_COMPARE))
                    ? window.localStorage.getItem(STORAGE_COMPARE)
                    : "previous_period",
            },
        });
        this._refreshTimer = null;
        this._searchTimers = {};
        this._onKeydown = (ev) => this.onGlobalKeydown(ev);
        this._onVisibility = () => {
            if (document.hidden) {
                this.clearAutoRefresh();
            } else {
                this.syncAutoRefresh();
            }
        };
        onWillStart(async () => {
            await this.bootstrap();
        });
        onMounted(() => {
            this.syncAutoRefresh();
            window.addEventListener("keydown", this._onKeydown);
            document.addEventListener("visibilitychange", this._onVisibility);
        });
        onWillUnmount(() => {
            this.clearAutoRefresh();
            window.removeEventListener("keydown", this._onKeydown);
            document.removeEventListener("visibilitychange", this._onVisibility);
        });
    }

    get visibleDashboards() {
        return (this.state.dashboards || []).filter((item) => item.available);
    }

    get unavailableDashboards() {
        return (this.state.dashboards || []).filter((item) => !item.available);
    }

    get navGroups() {
        const byKey = Object.fromEntries((this.visibleDashboards || []).map((item) => [item.key, item]));
        return NAV_GROUPS.map((group) => ({
            ...group,
            items: group.keys.map((key) => byKey[key]).filter(Boolean),
        })).filter((group) => group.items.length);
    }

    get activeDashboard() {
        return this.visibleDashboards.find((item) => item.key === this.state.activeKey) || this.visibleDashboards[0];
    }

    get chartEntries() {
        return Object.entries(this.state.payload.charts || {});
    }

    get tableEntries() {
        return Object.entries(this.state.payload.tables || {});
    }

    get lastUpdatedLabel() {
        const stamp = this.state.payload?.meta?.generated_at;
        if (!stamp) {
            return "";
        }
        try {
            return new Date(stamp).toLocaleString();
        } catch (_error) {
            return stamp;
        }
    }

    get hasPayload() {
        return Boolean(this.state.payload && this.state.payload.meta && this.state.payload.meta.dashboard);
    }

    get canAutoRefresh() {
        return LIVE_DASHBOARDS.has(this.state.activeKey);
    }

    get periodChips() {
        return this.isExecutiveShell ? EXEC_PERIODS : PRIMARY_PERIODS;
    }

    get filterSummaryLabel() {
        const periodKey = this.state.filters.period;
        const period =
            this.periodChips.find((item) => item.key === periodKey)?.label
            || this.extraPeriods.find((item) => item.key === periodKey)?.label
            || periodKey;
        const compareLabels = {
            none: "Compare off",
            previous_period: "vs previous",
            previous_year: "vs year ago",
        };
        const compare = compareLabels[this.state.filters.compare_period] || "";
        return compare ? `${period} · ${compare}` : period;
    }

    get extraPeriods() {
        const primary = new Set(this.periodChips.map((item) => item.key));
        const fromPrimary = PRIMARY_PERIODS.filter((item) => !primary.has(item.key));
        const fromServer = (this.state.periods || []).filter(
            (item) => !primary.has(item.key) && !fromPrimary.some((period) => period.key === item.key)
        );
        return fromPrimary.concat(fromServer);
    }

    get executiveBriefing() {
        if (!this.isExecutiveShell || !this.hasPayload) {
            return null;
        }
        const commentary = this.state.payload.commentary || [];
        const queues = this.rankedWorkbenchQueues;
        const top = queues[0];
        const movers = (this.state.payload.kpis || [])
            .filter((kpi) => !kpi.unavailable && kpi.percent !== false && kpi.percent !== undefined)
            .sort((left, right) => Math.abs(right.percent || 0) - Math.abs(left.percent || 0));
        const topDelta = movers[0];
        const profit = this.kpiByKey("profit");
        const cash = this.kpiByKey("cash");
        let headline = commentary[0] || "";
        if (!headline) {
            const bits = [];
            if (profit && !profit.unavailable) {
                bits.push(`Net result ${profit.formatted}`);
            }
            if (cash && !cash.unavailable) {
                bits.push(`cash ${cash.formatted}`);
            }
            if (top) {
                bits.push(`${top.count} ${String(top.title || "exceptions").toLowerCase()} lead credit risk`);
            }
            headline = bits.length
                ? `${bits.join("; ")}.`
                : "No material exceptions flagged in this scope.";
        }
        const facts = [];
        if (commentary[1]) {
            facts.push(commentary[1]);
        } else if (topDelta && this.state.filters.compare_period !== "none") {
            const pct = Number(topDelta.percent || 0).toFixed(1);
            facts.push(`${topDelta.label}: ${pct}% vs ${topDelta.comparison_label || "comparison"}`);
        }
        if (top && facts.length < 2) {
            const exposure = top.amount_formatted || `${top.count} items`;
            const age = top.oldest_days !== false && top.oldest_days !== undefined ? `${top.oldest_days}d` : "—";
            facts.push(`${top.title}: ${exposure} · oldest ${age}`);
        }
        return {
            headline,
            facts: facts.slice(0, 2),
            primaryAction: top?.action_key || false,
            primaryLabel: top ? `Review · ${top.title}` : "",
            hasTop: Boolean(top),
        };
    }

    get rankedWorkbenchQueues() {
        return [...this.visibleAlerts]
            .sort((left, right) => (
                (SEVERITY_RANK[left.severity] ?? 3) - (SEVERITY_RANK[right.severity] ?? 3)
                || (right.amount || 0) - (left.amount || 0)
                || (right.oldest_days || 0) - (left.oldest_days || 0)
            ))
            .map((queue, index) => ({ ...queue, rank: index + 1 }));
    }

    get currency() {
        return this.state.payload?.meta?.currency || {};
    }

    get warningPreview() {
        const warnings = this.state.payload?.meta?.warnings || [];
        return warnings[0] || "";
    }

    get isExecutiveShell() {
        const payload = this.state.payload || {};
        return (
            this.state.activeKey === "executive"
            || payload.meta?.dashboard === "executive"
            || payload.layout?.kind === "executive"
        );
    }

    get layoutSections() {
        const payload = this.state.payload || {};
        const layout = payload.layout || {};
        if (layout.sections && layout.sections.length) {
            const sections = layout.sections.slice();
            if (!sections.some((section) => section.type === "more")) {
                sections.push({ id: "more", type: "more", span: 12, keys: [], title: "More indicators" });
            }
            return sections;
        }
        const sections = [];
        if ((payload.commentary || []).length) {
            sections.push({ id: "commentary", type: "commentary", span: 12, keys: [] });
        }
        if ((payload.kpis || []).length) {
            sections.push({ id: "hero", type: "kpis", span: 12, keys: (payload.kpis || []).slice(0, 5).map((kpi) => kpi.key), hero: true });
        }
        Object.keys(payload.charts || {}).forEach((key, index) => {
            sections.push({ id: `chart_${key}`, type: "charts", keys: [key], span: index === 0 ? 8 : 4 });
        });
        if ((payload.quality_cards || []).length) {
            sections.push({ id: "quality", type: "quality", span: 12, keys: [] });
        }
        if ((payload.alerts || []).length) {
            sections.push({ id: "alerts", type: "alerts", span: 12, keys: [] });
        }
        Object.keys(payload.tables || {}).forEach((key) => {
            sections.push({ id: `table_${key}`, type: "tables", keys: [key], span: 12 });
        });
        return sections;
    }

    get moreBundle() {
        const used = new Set();
        (this.layoutSections || []).forEach((section) => {
            (section.keys || []).forEach((key) => used.add(`${section.type}:${key}`));
            if (section.type === "watchlist") {
                (section.keys || []).forEach((key) => used.add(`tables:${key}`));
            }
            if (section.type === "more") {
                (section.keys || []).forEach((key) => used.add(`kpis:${key}`));
            }
        });
        const payload = this.state.payload || {};
        const kpis = (payload.kpis || []).filter((kpi) => !used.has(`kpis:${kpi.key}`));
        const charts = Object.entries(payload.charts || {}).filter(([key]) => !used.has(`charts:${key}`));
        const tables = Object.entries(payload.tables || {}).filter(([key]) => !used.has(`tables:${key}`));
        const moreSection = (this.layoutSections || []).find((section) => section.type === "more");
        const listed = (moreSection?.keys || []).map((key) => this.kpiByKey(key)).filter(Boolean);
        const extraKpis = [
            ...listed,
            ...kpis.filter((kpi) => !listed.some((item) => item.key === kpi.key)),
        ];
        return {
            kpis: extraKpis,
            charts,
            tables,
            hasMore: Boolean(extraKpis.length || charts.length || tables.length),
        };
    }

    get queueGroups() {
        const alerts = this.visibleAlerts;
        const groups = { cash: [], delivery: [], people: [], commercial: [] };
        alerts.forEach((queue) => {
            const key = groups[queue.group] ? queue.group : "commercial";
            groups[key].push(queue);
        });
        return Object.entries(groups)
            .map(([key, items]) => ({
                key,
                label: QUEUE_GROUP_LABELS[key],
                items: items.sort((a, b) => {
                    const rank = { danger: 0, warning: 1, info: 2 };
                    return (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3)
                        || (b.amount || 0) - (a.amount || 0)
                        || (b.oldest_days || 0) - (a.oldest_days || 0);
                }),
            }))
            .filter((group) => group.items.length);
    }

    get visibleAlerts() {
        const open = this.state.payload.alerts || this.state.payload.queues || [];
        if (this.state.showCleared) {
            return open.concat(this.state.payload.cleared || []);
        }
        return open.filter((queue) => queue.count);
    }

    get activeChips() {
        const chips = [];
        const filters = this.state.filters;
        const pushIds = (ids, options, label, field) => {
            (ids || []).forEach((id) => {
                const option = (options || []).find((item) => item.id === id);
                chips.push({ field, id, label: `${label}: ${option ? option.name : id}` });
            });
        };
        pushIds(filters.company_ids.length === (this.state.options.companies || []).length ? [] : filters.company_ids, this.state.options.companies, "Company", "company_ids");
        pushIds(filters.sub_company_ids, [{ id: 0, name: "Unassigned" }, ...(this.state.options.sub_companies || [])], "Active company", "sub_company_ids");
        MULTI_FILTERS.forEach(([key, listField, , optionKey, placeholder]) => {
            pushIds(filters[listField], this.filterOptions(optionKey, key), placeholder.replace("All ", ""), listField);
        });
        if (filters.approval_status) {
            chips.push({ field: "approval_status", id: filters.approval_status, label: `Approval: ${filters.approval_status}` });
        }
        if (filters.document_status) {
            chips.push({ field: "document_status", id: filters.document_status, label: `Status: ${filters.document_status}` });
        }
        if (filters.labour_category) {
            chips.push({ field: "labour_category", id: filters.labour_category, label: `Labour: ${filters.labour_category}` });
        }
        return chips;
    }

    get contextualFilters() {
        return MULTI_FILTERS
            .filter(([key, , , optionKey]) => this.showFilter(key) && (this.filterOptions(optionKey, key) || []).length)
            .map(([key, listField, scalar, optionKey, placeholder]) => ({
                key,
                listField,
                field: scalar,
                placeholder,
                kind: "id",
                searchable: SEARCH_KINDS.has(key),
                options: this.filterOptions(optionKey, key),
            }));
    }

    filterOptions(optionKey, kind) {
        const searched = this.state.searchOptions[kind];
        if (searched && searched.length) {
            return searched;
        }
        return this.state.options[optionKey] || [];
    }

    kpiByKey(key) {
        return (this.state.payload.kpis || []).find((kpi) => kpi.key === key);
    }

    chartByKey(key) {
        return (this.state.payload.charts || {})[key];
    }

    tableByKey(key) {
        return (this.state.payload.tables || {})[key];
    }

    tableEntry(key) {
        const table = this.tableByKey(key);
        return table ? this.tableView([key, table]) : false;
    }

    sectionKpis(section) {
        const keys = section.keys || [];
        if (!keys.length) {
            return this.state.payload.kpis || [];
        }
        const matched = keys.map((key) => this.kpiByKey(key)).filter(Boolean);
        if (!matched.length && section.hero) {
            return (this.state.payload.kpis || []).slice(0, 5);
        }
        return matched;
    }

    isCommandHero(section) {
        return Boolean(section?.hero && (section.variant === "command" || this.isExecutiveShell));
    }

    heroPrimaryKpis(section) {
        return this.sectionKpis(section).slice(0, 2);
    }

    heroSecondaryKpis(section) {
        return this.sectionKpis(section).slice(2);
    }

    isBriefingAlerts(section) {
        return Boolean(section?.variant === "briefing" || this.isExecutiveShell);
    }

    flatAlertQueues(section) {
        if (!this.isBriefingAlerts(section)) {
            return [];
        }
        if (this.isExecutiveShell) {
            return this.rankedWorkbenchQueues;
        }
        const keys = section.keys || [];
        const alerts = this.visibleAlerts;
        if (!keys.length) {
            return alerts;
        }
        const ordered = keys.map((key) => alerts.find((item) => item.key === key)).filter(Boolean);
        const extras = alerts.filter((item) => !keys.includes(item.key));
        return ordered.concat(extras);
    }

    showKpiDelta(kpi) {
        if (!kpi || kpi.unavailable || kpi.percent === false || kpi.percent === undefined) {
            return false;
        }
        return this.state.filters.compare_period !== "none";
    }

    kpiCompareLabel(kpi) {
        if (this.state.filters.compare_period === "none") {
            return "Compare off";
        }
        return kpi.comparison_label || "";
    }

    toggleKpiFocus(kpi) {
        if (!kpi?.key) {
            return;
        }
        this.state.focusedKpi = this.state.focusedKpi === kpi.key ? false : kpi.key;
    }

    kpiFocusClass(kpi) {
        if (!this.state.focusedKpi) {
            return "";
        }
        return this.state.focusedKpi === kpi.key ? " is-focused" : " is-dimmed";
    }

    isChartEmphasized(chartKey) {
        const focus = this.state.focusedKpi;
        if (!focus) {
            return false;
        }
        if (focus === "revenue" || focus === "profit") {
            return chartKey === "pnl";
        }
        if (focus === "cash") {
            return chartKey === "cash" || chartKey === "cash_comp";
        }
        if (focus === "receivables") {
            return chartKey === "cash_comp";
        }
        if (focus === "ra_work") {
            return chartKey === "backlog";
        }
        return false;
    }

    focusQueue(queue) {
        if (!queue?.key) {
            return;
        }
        this.state.focusedQueue = this.state.focusedQueue === queue.key ? false : queue.key;
        if (this.state.focusedQueue) {
            const watchKey = this.relatedWatchlistKey(queue);
            if (watchKey) {
                this.state.watchlistExpanded = { ...this.state.watchlistExpanded, [watchKey]: true };
            }
        }
    }

    relatedWatchlistKey(queue) {
        const title = String(queue?.title || queue?.key || "").toLowerCase();
        if (title.includes("customer") || title.includes("invoice") || title.includes("receivable")) {
            return "overdue_customers";
        }
        if (title.includes("contract") || title.includes("expir")) {
            return "expiring";
        }
        if (title.includes("vendor") || title.includes("bill")) {
            return "overdue_customers";
        }
        return "overdue_customers";
    }

    isWatchlistRelated(tableKey) {
        if (!this.state.focusedQueue) {
            return false;
        }
        const queue = this.rankedWorkbenchQueues.find((item) => item.key === this.state.focusedQueue);
        return Boolean(queue && this.relatedWatchlistKey(queue) === tableKey);
    }

    queueFocusClass(queue) {
        if (!this.state.focusedQueue) {
            return "";
        }
        return this.state.focusedQueue === queue.key ? " is-focused" : " is-dimmed";
    }

    watchlistSide(key, limit = 5) {
        const table = this.tableByKey(key);
        if (!table) {
            return false;
        }
        const rows = table.rows || [];
        const expanded = Boolean(this.state.watchlistExpanded[key]);
        return {
            key,
            title: table.title,
            columns: table.columns || [],
            rows: expanded ? rows : rows.slice(0, limit),
            total: rows.length,
            empty: table.empty || "No records in this scope.",
            expanded,
            limit,
        };
    }

    toggleWatchlist(key) {
        this.state.watchlistExpanded = {
            ...this.state.watchlistExpanded,
            [key]: !this.state.watchlistExpanded[key],
        };
    }

    chartSeriesLabels(key) {
        return (this.chartByKey(key)?.datasets || [])
            .map((dataset) => dataset.label)
            .filter(Boolean);
    }

    isSeriesVisible(key, label) {
        return !this.state.chartSeriesHidden[key]?.[label];
    }

    toggleChartSeries(key, label) {
        const current = { ...(this.state.chartSeriesHidden[key] || {}) };
        current[label] = !current[label];
        const labels = this.chartSeriesLabels(key);
        if (labels.length && labels.every((item) => current[item])) {
            return;
        }
        this.state.chartSeriesHidden = {
            ...this.state.chartSeriesHidden,
            [key]: current,
        };
    }

    toggleHighlightLatest(key) {
        this.state.chartHighlightLatest = {
            ...this.state.chartHighlightLatest,
            [key]: !this.state.chartHighlightLatest[key],
        };
    }

    isHighlightLatest(key) {
        return Boolean(this.state.chartHighlightLatest[key]);
    }

    chartStatPills(key) {
        if (key !== "cash") {
            return [];
        }
        const spec = this.chartByKey(key);
        if (!spec || !this.chartHasData(spec)) {
            return [];
        }
        return (spec.datasets || []).map((dataset) => {
            const sum = (dataset.data || []).reduce((total, value) => total + (Number(value) || 0), 0);
            return {
                label: dataset.label,
                value: this.formatCompactMoney(sum),
            };
        });
    }

    formatCompactMoney(value) {
        const num = Number(value) || 0;
        const code = this.currency?.name || this.currency?.symbol || "";
        const abs = Math.abs(num);
        let scaled = num;
        let suffix = "";
        if (abs >= 1e6) {
            scaled = num / 1e6;
            suffix = "M";
        } else if (abs >= 1e3) {
            scaled = num / 1e3;
            suffix = "k";
        }
        const body = `${scaled.toFixed(suffix ? 1 : 0)}${suffix}`.replace(/\.0([kM])?$/, "$1");
        return `${body} ${code}`.trim();
    }

    openActionCenter() {
        this.switchDashboard("action_center");
    }

    suggestBroaderPeriod() {
        const current = this.state.filters.period;
        if (current === "month") {
            this.setPeriod("quarter");
            return;
        }
        if (current === "quarter") {
            this.setPeriod("ytd");
            return;
        }
        this.setPeriod("ytd");
    }

    chartHistoryNote(spec) {
        if (!spec || !this.chartHasData(spec)) {
            return "";
        }
        const type = spec.type || spec.variant;
        if (["doughnut", "pie", "gauge", "horizontalBar"].includes(type)) {
            return "";
        }
        const labels = spec.labels || [];
        const datasets = spec.datasets || [];
        if (labels.length < 3) {
            return "";
        }
        let active = 0;
        labels.forEach((_, index) => {
            if (datasets.some((dataset) => Number((dataset.data || [])[index]))) {
                active += 1;
            }
        });
        if (active <= 1) {
            return "Limited history — try Quarter or YTD for trend.";
        }
        if (active === 2 && labels.length >= 5) {
            return "Limited history — most prior periods are near zero.";
        }
        return "";
    }

    chartSpec(key) {
        const spec = this.chartByKey(key);
        if (!spec) {
            return spec;
        }
        const override = this.state.chartTypes[key];
        const hiddenMap = this.state.chartSeriesHidden[key] || {};
        const forceType = override && ["bar", "line", "area"].includes(override) ? override : false;
        const datasets = (spec.datasets || []).map((dataset) => {
            const next = {
                label: dataset.label,
                data: Array.isArray(dataset.data) ? dataset.data.slice() : [],
                hidden: Boolean(dataset.hidden) || Boolean(hiddenMap[dataset.label]),
                fill: dataset.fill,
                borderDash: dataset.borderDash,
                order: dataset.order,
                yAxisID: dataset.yAxisID,
            };
            if (forceType) {
                next.type = forceType === "area" ? "line" : forceType;
            } else if (dataset.type) {
                next.type = dataset.type;
            }
            return next;
        });
        return {
            title: spec.title,
            subtitle: spec.subtitle,
            unit: spec.unit,
            labels: Array.isArray(spec.labels) ? spec.labels.slice() : [],
            datasets,
            type: forceType || spec.type,
            variant: forceType ? forceType : spec.variant,
            size: spec.size,
            stacked: forceType ? forceType === "bar" && spec.stacked : spec.stacked,
            allow_toggle: spec.allow_toggle,
            why_key: spec.why_key,
            action_key: spec.action_key,
            group_field: spec.group_field,
            label_ids: spec.label_ids,
            center_label: spec.center_label,
            heatstrip: spec.heatstrip,
            empty: spec.empty,
            y_begin_at_zero: spec.y_begin_at_zero,
            fill: (forceType || spec.type) === "area",
            force_dataset_type: forceType || false,
            highlight_latest: Boolean(this.state.chartHighlightLatest[key]),
            series_sig: `${JSON.stringify(hiddenMap)}|${forceType || ""}|${this.state.chartHighlightLatest[key] ? 1 : 0}`,
        };
    }

    setChartType(key, type) {
        if (!key || !["bar", "line", "area"].includes(type)) {
            return;
        }
        if (this.state.chartTypes[key] === type) {
            return;
        }
        this.state.chartTypes = {
            ...this.state.chartTypes,
            [key]: type,
        };
    }

    onKpiInfoClick(kpi, ev) {
        if (ev) {
            ev.stopPropagation();
            ev.preventDefault();
        }
        if (!kpi || !kpi.key) {
            return;
        }
        this.openInspector(kpi);
    }

    onChartWhyClick(chartKey, ev) {
        if (ev) {
            ev.stopPropagation();
            ev.preventDefault();
        }
        const spec = this.chartByKey(chartKey);
        const kpi = spec?.why_key ? this.kpiByKey(spec.why_key) : false;
        if (!kpi) {
            return;
        }
        this.openInspector(kpi);
    }

    openInspector(kpi) {
        if (!kpi || !kpi.key) {
            return;
        }
        this.state.selectedKpi = kpi;
        setTimeout(() => {
            const close = this.inspectorRef.el && this.inspectorRef.el.querySelector("button");
            if (close) {
                close.focus();
            }
        }, 0);
    }

    sectionAlerts(section) {
        const keys = section.keys || [];
        const alerts = this.visibleAlerts;
        if (!keys.length) {
            return alerts;
        }
        return keys.map((key) => alerts.find((item) => item.key === key)).filter(Boolean);
    }

    chartTypeActive(key, type) {
        const spec = this.chartByKey(key) || {};
        const current = this.state.chartTypes[key] || spec.type || "bar";
        const normalized = current === "area"
            ? "area"
            : (current === "line" ? "line" : "bar");
        return normalized === type;
    }

    isNumericColumn(col) {
        const key = String(col?.key || "").toLowerCase();
        return /amount|residual|value|balance|total|debit|credit|qty|count|hours|percent|net/.test(key);
    }

    qualityCards(section) {
        const cards = this.state.payload.quality_cards || [];
        const keys = section.keys || [];
        if (!keys.length) {
            return cards;
        }
        return keys.map((key) => cards.find((card) => card.key === key)).filter(Boolean);
    }

    loadCollapsed() {
        try {
            return JSON.parse(window.localStorage.getItem(STORAGE_COLLAPSED) || "{}");
        } catch (_error) {
            return {};
        }
    }

    isCollapsed(section) {
        return Boolean(this.state.collapsed[`${this.state.activeKey}:${section}`]);
    }

    toggleSection(section) {
        const key = `${this.state.activeKey}:${section}`;
        this.state.collapsed[key] = !this.state.collapsed[key];
        window.localStorage.setItem(STORAGE_COLLAPSED, JSON.stringify(this.state.collapsed));
    }

    showFilter(name) {
        const key = this.state.activeKey;
        const allowed = this.state.filterCatalog[key] || [
            "company",
            "sub_company",
            "project",
            "contract",
        ];
        return allowed.includes(name);
    }

    readUrlState() {
        try {
            const params = new URLSearchParams(window.location.search);
            return {
                dashboard: params.get("dashboard"),
                period: params.get("period"),
            };
        } catch (_error) {
            return {};
        }
    }

    writeUrlState() {
        try {
            const url = new URL(window.location.href);
            url.searchParams.set("dashboard", this.state.activeKey);
            url.searchParams.set("period", this.state.filters.period);
            window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
        } catch (_error) {
            // Action service URL rewrite is optional.
        }
    }

    rpcFilters() {
        const filters = { ...this.state.filters };
        const mapOne = (source, target) => {
            if (Array.isArray(filters[target]) && filters[target].length) {
                filters[target] = filters[target].map((id) => parseInt(id, 10));
                return;
            }
            if (filters[source]) {
                filters[target] = [parseInt(filters[source], 10)];
            }
        };
        mapOne("project_id", "project_ids");
        mapOne("contract_id", "contract_ids");
        mapOne("partner_id", "partner_ids");
        mapOne("vendor_id", "vendor_ids");
        mapOne("department_id", "department_ids");
        mapOne("warehouse_id", "warehouse_ids");
        mapOne("employee_id", "employee_ids");
        mapOne("product_id", "product_ids");
        mapOne("product_category_id", "product_category_ids");
        mapOne("location_id", "location_ids");
        mapOne("journal_id", "journal_ids");
        mapOne("account_id", "account_ids");
        mapOne("analytic_account_id", "analytic_account_ids");
        mapOne("salesperson_id", "salesperson_ids");
        mapOne("sales_team_id", "sales_team_ids");
        mapOne("requester_id", "requester_ids");
        if (filters.approval_status) {
            filters.approval_statuses = [filters.approval_status];
        }
        if (filters.document_status) {
            filters.document_statuses = [filters.document_status];
        }
        if (filters.labour_category) {
            filters.labour_categories = [filters.labour_category];
        }
        if (Array.isArray(filters.company_ids) && filters.company_ids.length) {
            filters.company_ids = filters.company_ids.map((id) => parseInt(id, 10));
        } else if (filters.company_id) {
            filters.company_ids = [parseInt(filters.company_id, 10)];
        }
        filters.dashboard = this.state.activeKey;
        filters.limit = this.state.pageSize || 10;
        const keepEmpty = new Set(["company_ids", "sub_company_ids"]);
        Object.keys(filters).forEach((key) => {
            if (Array.isArray(filters[key]) && !filters[key].length && !keepEmpty.has(key)) {
                delete filters[key];
            }
        });
        return filters;
    }

    async bootstrap() {
        this.state.loading = true;
        try {
            const context = await this.orm.call("ages.enterprise.dashboard", "get_dashboard_context", [this.rpcFilters()]);
            this.state.dashboards = context.dashboards || [];
            this.state.periods = context.periods || [];
            this.state.comparePeriods = context.compare_periods || [];
            this.state.filterCatalog = context.filter_catalog || {};
            this.state.defaultDashboard = context.default_dashboard || "executive";
            const stored = window.localStorage.getItem(STORAGE_KEY);
            const urlState = this.readUrlState();
            if (urlState.period && PERIOD_KEYS.has(urlState.period)) {
                this.state.filters.period = urlState.period;
            }
            const available = this.visibleDashboards.map((item) => item.key);
            const preferred = urlState.dashboard || stored || this.state.defaultDashboard;
            this.state.activeKey = available.includes(preferred) ? preferred : (available[0] || "executive");
            await this.loadOptions();
            await this.reload();
            this.writeUrlState();
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || "Unable to load dashboard.";
            this.state.loading = false;
        }
    }

    async loadOptions() {
        this.state.options = await this.orm.call("ages.enterprise.dashboard", "get_filter_options", [this.rpcFilters()]);
        if (!this.state.filters.company_ids.length && this.state.options.companies.length) {
            this.state.filters.company_ids = this.state.options.companies.map((company) => company.id);
        }
    }

    async reload() {
        const keepVisible = this.hasPayload;
        this.state.loading = !keepVisible;
        this.state.refreshing = keepVisible;
        this.state.error = false;
        const token = (this._token = (this._token || 0) + 1);
        try {
            const payload = await this.orm.call("ages.enterprise.dashboard", "get_dashboard", [
                this.state.activeKey,
                this.rpcFilters(),
            ]);
            if (token !== this._token) {
                return;
            }
            this.state.payload = payload;
            this.state.sort = {};
            this.state.tablePage = {};
            this.state.selectedKpi = false;
            this.state.chartTypes = {};
            this.writeUrlState();
        } catch (error) {
            if (token !== this._token) {
                return;
            }
            this.state.error = error?.data?.message || error?.message || "Unable to load this dashboard.";
            if (!keepVisible) {
                this.state.payload = { meta: {}, kpis: [], charts: {}, tables: {}, alerts: [] };
            }
        }
        this.state.loading = false;
        this.state.refreshing = false;
    }

    async switchDashboard(key) {
        const item = (this.state.dashboards || []).find((dash) => dash.key === key);
        if (!item || !item.available) {
            return;
        }
        this.state.activeKey = key;
        this.state.moreIndicators = false;
        this.closeNav();
        window.localStorage.setItem(STORAGE_KEY, key);
        await this.loadOptions();
        await this.reload();
    }

    _isMobileNav() {
        return typeof window !== "undefined"
            && window.matchMedia("(max-width: 991.98px)").matches;
    }

    toggleNav() {
        if (this._isMobileNav()) {
            this.state.navOpen = !this.state.navOpen;
            return;
        }
        this.state.navCollapsed = !this.state.navCollapsed;
        this.state.navOpen = false;
        window.localStorage.setItem(
            STORAGE_NAV_COLLAPSED,
            this.state.navCollapsed ? "1" : "0"
        );
    }

    closeNav() {
        // Mobile drawer only — keep desktop rail open when switching dashboards.
        this.state.navOpen = false;
    }

    collapseNav() {
        this.state.navOpen = false;
        if (!this._isMobileNav()) {
            this.state.navCollapsed = true;
            window.localStorage.setItem(STORAGE_NAV_COLLAPSED, "1");
        }
    }

    toggleMobileFilters() {
        this.state.mobileFiltersOpen = !this.state.mobileFiltersOpen;
        if (!this.state.mobileFiltersOpen) {
            this.state.morePeriods = false;
            this.state.openDropdown = false;
        }
    }

    closeMobileFilters() {
        this.state.mobileFiltersOpen = false;
        this.state.morePeriods = false;
        this.state.openDropdown = false;
    }

    onGlobalKeydown(ev) {
        if (ev.key === "Tab" && this.state.selectedKpi) {
            this.trapInspector(ev);
            return;
        }
        if (ev.key !== "Escape") {
            return;
        }
        if (this.state.selectedKpi) {
            this.closeWhyPanel();
            return;
        }
        if (this.state.openDropdown) {
            this.state.openDropdown = false;
            return;
        }
        if (this.state.mobileFiltersOpen) {
            this.closeMobileFilters();
            return;
        }
        if (this.state.navOpen) {
            this.closeNav();
        }
    }

    trapInspector(ev) {
        const root = this.inspectorRef.el;
        if (!root) {
            return;
        }
        const focusable = [...root.querySelectorAll("button, [href], input, select, textarea")].filter((el) => !el.disabled);
        if (!focusable.length) {
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (ev.shiftKey && document.activeElement === first) {
            ev.preventDefault();
            last.focus();
        } else if (!ev.shiftKey && document.activeElement === last) {
            ev.preventDefault();
            first.focus();
        }
    }

    persistPeriod(period) {
        if (PERIOD_KEYS.has(period)) {
            window.localStorage.setItem(STORAGE_PERIOD, period);
        }
    }

    persistCompare(compare) {
        if (COMPARE_KEYS.has(compare)) {
            window.localStorage.setItem(STORAGE_COMPARE, compare);
        }
    }

    setPeriod(period) {
        this.state.filters.period = period;
        this.state.morePeriods = false;
        this.persistPeriod(period);
        this.reload();
    }

    onPeriodChange(ev) {
        this.setPeriod(ev.target.value);
    }

    setCompare(compare) {
        this.state.filters.compare_period = compare;
        this.persistCompare(compare);
        this.reload();
    }

    onCompareChange(ev) {
        this.setCompare(ev.target.value);
    }

    onDateFromChange(ev) {
        this.state.filters.date_from = ev.target.value;
        this.state.filters.period = "custom";
        this.persistPeriod("custom");
        this.reload();
    }

    onDateToChange(ev) {
        this.state.filters.date_to = ev.target.value;
        this.state.filters.period = "custom";
        this.persistPeriod("custom");
        this.reload();
    }

    toggleDropdown(name) {
        this.state.openDropdown = this.state.openDropdown === name ? false : name;
    }

    toggleId(field, id) {
        const current = [...(this.state.filters[field] || [])];
        const parsed = typeof id === "number" ? id : parseInt(id, 10);
        const index = current.indexOf(parsed);
        if (index >= 0) {
            current.splice(index, 1);
        } else {
            current.push(parsed);
        }
        this.state.filters[field] = current;
        const scalar = field.replace(/s$/, "").replace("ids", "id");
        this.state.filters[scalar] = current[0] || false;
        if (field === "company_ids") {
            this.loadOptions().then(() => this.reload());
            return;
        }
        this.reload();
    }

    isSelected(field, id) {
        return (this.state.filters[field] || []).includes(id);
    }

    onSelectChange(field, ev) {
        const value = ev.target.value;
        const parsed = value ? parseInt(value, 10) : false;
        if (field === "sub_company_id") {
            this.state.filters.sub_company_ids = value === "" ? [] : [parsed];
        } else {
            this.state.filters[field] = parsed;
        }
        if (field === "company_id") {
            this.loadOptions().then(() => this.reload());
            return;
        }
        this.reload();
    }

    onValueChange(field, ev) {
        this.state.filters[field] = ev.target.value || false;
        this.reload();
    }

    removeChip(chip) {
        if (Array.isArray(this.state.filters[chip.field])) {
            this.state.filters[chip.field] = this.state.filters[chip.field].filter((id) => id !== chip.id);
        } else {
            this.state.filters[chip.field] = false;
        }
        this.reload();
    }

    onFilterSearch(kind, ev) {
        const query = ev.target.value || "";
        this.state.searchQuery[kind] = query;
        if (this._searchTimers[kind]) {
            clearTimeout(this._searchTimers[kind]);
        }
        this._searchTimers[kind] = setTimeout(async () => {
            try {
                const rows = await this.orm.call("ages.enterprise.dashboard", "get_filter_search", [
                    kind, query, this.rpcFilters(),
                ]);
                this.state.searchOptions[kind] = rows || [];
            } catch (_error) {
                this.state.searchOptions[kind] = [];
            }
        }, 300);
    }

    onAutoRefreshChange(ev) {
        this.state.autoRefresh = Boolean(ev.target.checked);
        window.localStorage.setItem(STORAGE_REFRESH, this.state.autoRefresh ? "1" : "0");
        this.syncAutoRefresh();
    }

    toggleUnavailable() {
        this.state.showUnavailable = !this.state.showUnavailable;
        window.localStorage.setItem(STORAGE_UNAVAILABLE, this.state.showUnavailable ? "1" : "0");
    }

    syncAutoRefresh() {
        this.clearAutoRefresh();
        if (this.state.autoRefresh && this.canAutoRefresh && !document.hidden) {
            this._refreshTimer = setInterval(() => this.reload(), 60000);
        }
    }

    clearAutoRefresh() {
        if (this._refreshTimer) {
            clearInterval(this._refreshTimer);
            this._refreshTimer = null;
        }
    }

    async openAction(actionKey, extraDomain = null) {
        if (!actionKey) {
            return;
        }
        try {
            const action = await this.orm.call("ages.enterprise.dashboard", "open_action", [
                actionKey,
                this.rpcFilters(),
                extraDomain,
            ]);
            if (action) {
                this.action.doAction(action);
            }
        } catch (error) {
            this.notification.add(error?.data?.message || "Unable to open records.", { type: "danger" });
        }
    }

    onKpiValueClick(kpi) {
        if (!kpi || kpi.unavailable) {
            this.openInspector(kpi);
            return;
        }
        if (kpi.action_key) {
            this.openAction(kpi.action_key);
        }
    }

    onKpiClick(kpi) {
        this.onKpiValueClick(kpi);
    }

    closeWhyPanel() {
        this.state.selectedKpi = false;
    }

    resetFilters() {
        const companies = (this.state.options.companies || []).map((company) => company.id);
        this.state.filters = {
            ...emptyFilters(),
            company_ids: companies,
        };
        this.persistPeriod("month");
        this.persistCompare("previous_period");
        this.loadOptions().then(() => this.reload());
    }

    onChartSelect(spec, payload) {
        if (!payload) {
            return;
        }
        if (payload.actionKey && payload.groupField && payload.resId) {
            this.openAction(payload.actionKey, [[payload.groupField, "=", payload.resId]]);
            return;
        }
        if (spec.action_key && payload.resId && spec.group_field) {
            this.openAction(spec.action_key, [[spec.group_field, "=", payload.resId]]);
        }
    }

    onHeatstripClick(spec, cell) {
        if (!spec || !spec.action_key) {
            return;
        }
        this.openAction(spec.action_key);
    }

    onRowClick(row) {
        if (row.action_key) {
            const value = row.res_value !== undefined ? row.res_value : row.res_id;
            const operator = row.res_operator || "=";
            const extra = value && row.res_field
                ? [[row.res_field, operator, value]]
                : (row.res_id ? [["id", "=", row.res_id]] : null);
            this.openAction(row.action_key, extra);
        }
    }

    sparkSpec(kpi) {
        const spark = kpi?.sparkline;
        if (!spark) {
            return false;
        }
        return {
            type: "area",
            variant: "sparkline",
            title: kpi.label,
            labels: Array.isArray(spark.labels) ? spark.labels.slice() : [],
            datasets: [{ label: kpi.label, data: Array.isArray(spark.data) ? spark.data.slice() : [] }],
            unit: spark.unit || kpi.kind || "money",
            size: "spark",
            empty: false,
        };
    }

    targetPercent(kpi) {
        if (!kpi || !kpi.target) {
            return 0;
        }
        const value = Number(kpi.value) || 0;
        const target = Number(kpi.target) || 0;
        if (!target) {
            return 0;
        }
        return Math.max(0, Math.min(100, Math.round((value / target) * 100)));
    }

    directionClass(kpi) {
        if (kpi.unavailable) {
            return "is-unavailable";
        }
        if (kpi.direction === "up") {
            return "is-up";
        }
        if (kpi.direction === "down") {
            return "is-down";
        }
        return "is-flat";
    }

    sortTable(tableKey, columnKey) {
        const current = this.state.sort[tableKey] || {};
        const dir = current.key === columnKey && current.dir === "asc" ? "desc" : "asc";
        this.state.sort[tableKey] = { key: columnKey, dir };
        this.state.tablePage[tableKey] = 0;
    }

    tableView(entry) {
        const key = entry[0];
        const table = entry[1] || {};
        const rows = [...(table.rows || [])];
        const sort = this.state.sort[key];
        if (sort && sort.key) {
            rows.sort((left, right) => {
                const rawKey = `${sort.key}_raw`;
                const a = left[rawKey] !== undefined ? left[rawKey] : left[sort.key];
                const b = right[rawKey] !== undefined ? right[rawKey] : right[sort.key];
                const aNum = typeof a === "number" ? a : parseFloat(String(a).replace(/[^0-9.-]/g, ""));
                const bNum = typeof b === "number" ? b : parseFloat(String(b).replace(/[^0-9.-]/g, ""));
                let cmp = 0;
                if (!Number.isNaN(aNum) && !Number.isNaN(bNum) && String(a).match(/[0-9]/) && String(b).match(/[0-9]/)) {
                    cmp = aNum - bNum;
                } else {
                    cmp = String(a || "").localeCompare(String(b || ""));
                }
                return sort.dir === "desc" ? -cmp : cmp;
            });
        }
        const pageSize = this.state.pageSize || 10;
        const page = this.state.tablePage[key] || 0;
        const pages = Math.max(1, Math.ceil(rows.length / pageSize));
        const safePage = Math.min(page, pages - 1);
        return {
            key,
            table,
            rows: rows.slice(safePage * pageSize, (safePage + 1) * pageSize),
            page: safePage,
            pages,
            total: rows.length,
            sort,
        };
    }

    setTablePage(tableKey, page) {
        this.state.tablePage[tableKey] = Math.max(0, page);
    }

    onPageSizeChange(ev) {
        const size = parseInt(ev.target.value, 10);
        this.state.pageSize = [5, 10, 20, 50].includes(size) ? size : 10;
        this.state.tablePage = {};
        window.localStorage.setItem(STORAGE_PAGE_SIZE, String(this.state.pageSize));
        this.reload();
    }

    chartHasData(spec) {
        if (!spec || spec.empty) {
            return false;
        }
        const labels = spec.labels || [];
        const datasets = spec.datasets || [];
        if (!labels.length || !datasets.length) {
            return false;
        }
        const type = spec.type || spec.variant;
        if (["doughnut", "pie", "gauge"].includes(type)) {
            return datasets.some((dataset) => (dataset.data || []).some((value) => Number(value)));
        }
        return true;
    }

    csvEscape(value) {
        const text = value === false || value === undefined || value === null ? "" : String(value);
        if (/[",\n]/.test(text)) {
            return `"${text.replace(/"/g, '""')}"`;
        }
        return text;
    }

    exportCsv() {
        const payload = this.state.payload || {};
        const blocks = [];
        const kpiLines = [["section", "key", "label", "value"].map((cell) => this.csvEscape(cell)).join(",")];
        (payload.kpis || []).forEach((kpi) => {
            kpiLines.push(["kpi", kpi.key, kpi.label, kpi.formatted].map((cell) => this.csvEscape(cell)).join(","));
        });
        blocks.push(kpiLines.join("\n"));
        Object.entries(payload.tables || {}).forEach(([tableKey, table]) => {
            const columns = table.columns || [];
            const header = [this.csvEscape(table.title || tableKey)];
            const colLine = columns.map((col) => this.csvEscape(col.label || col.key)).join(",");
            const rows = (table.rows || []).map((row) => columns.map((col) => this.csvEscape(row[col.key])).join(","));
            blocks.push([header.join(","), colLine, ...rows].join("\n"));
        });
        const csv = `\uFEFF${blocks.join("\n\n")}`;
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `ages-${this.state.activeKey}-dashboard.csv`;
        link.click();
        URL.revokeObjectURL(url);
    }

    printDashboard() {
        window.print();
    }
}

registry.category("actions").add("ages_enterprise_dashboard", AgesEnterpriseDashboard);
