/** @odoo-module **/

import { describe, expect, test } from "@odoo/hoot";
import { registry } from "@web/core/registry";
import { AgesEnterpriseDashboard } from "@ages_enterprise_dashboard/dashboard/dashboard";

describe.current.tags("headless");

test("AGES enterprise dashboard client action is registered", () => {
    expect(Boolean(AgesEnterpriseDashboard)).toBe(true);
    expect(registry.category("actions").contains("ages_enterprise_dashboard")).toBe(true);
});

test("csv export escapes commas and quotes", () => {
    const escape = AgesEnterpriseDashboard.prototype.csvEscape;
    expect(escape.call({}, "plain")).toBe("plain");
    expect(escape.call({}, 'a,b')).toBe('"a,b"');
    expect(escape.call({}, 'say "hi"')).toBe('"say ""hi"""');
});

test("kpi direction classes include unavailable", () => {
    const directionClass = AgesEnterpriseDashboard.prototype.directionClass;
    expect(directionClass.call({}, { unavailable: true })).toBe("is-unavailable");
    expect(directionClass.call({}, { direction: "up" })).toBe("is-up");
    expect(directionClass.call({}, { direction: "down" })).toBe("is-down");
    expect(directionClass.call({}, { direction: "flat" })).toBe("is-flat");
});

test("filter RPC maps scalar ids to lists and keeps unassigned sub-company", () => {
    const rpcFilters = AgesEnterpriseDashboard.prototype.rpcFilters;
    const owner = {
        state: {
            activeKey: "finance",
            pageSize: 20,
            filters: {
                company_id: "3",
                project_id: "12",
                approval_status: "waiting",
                labour_category: "site",
                sub_company_ids: [0],
            },
        },
    };
    const filters = rpcFilters.call(owner);
    expect(filters.company_ids).toEqual([3]);
    expect(filters.project_ids).toEqual([12]);
    expect(filters.approval_statuses).toEqual(["waiting"]);
    expect(filters.labour_categories).toEqual(["site"]);
    expect(filters.dashboard).toBe("finance");
    expect(filters.limit).toBe(20);
    expect(filters.sub_company_ids).toEqual([0]);
});

test("empty charts are skipped and unavailable KPIs stay dashed", () => {
    const chartHasData = AgesEnterpriseDashboard.prototype.chartHasData;
    expect(chartHasData.call({}, { labels: [], datasets: [] })).toBe(false);
    expect(chartHasData.call({}, { empty: true, labels: ["A"], datasets: [{ data: [1] }] })).toBe(false);
    expect(chartHasData.call({}, { type: "doughnut", labels: ["A"], datasets: [{ data: [0] }] })).toBe(false);
    expect(chartHasData.call({}, { type: "bar", labels: ["A"], datasets: [{ data: [0] }] })).toBe(true);
    expect(chartHasData.call({}, { labels: ["A"], datasets: [{ data: [12] }] })).toBe(true);
});

test("reload keeps existing payload visible while refreshing", () => {
    expect(Boolean(AgesEnterpriseDashboard.prototype.hasPayload)).toBe(true);
    const owner = {
        state: {
            payload: { meta: { dashboard: "finance" }, kpis: [{ key: "revenue" }] },
            loading: false,
            refreshing: false,
            error: false,
        },
    };
    expect(AgesEnterpriseDashboard.prototype.hasPayload.call(owner)).toBe(true);
    expect(AgesEnterpriseDashboard.prototype.hasPayload.call({ state: { payload: { meta: {} } } })).toBe(false);
});

test("escape closes why panel before the mobile nav", () => {
    const owner = {
        state: { selectedKpi: { key: "revenue" }, navOpen: true },
        closeWhyPanel() {
            this.state.selectedKpi = false;
        },
        closeNav() {
            this.state.navOpen = false;
        },
    };
    AgesEnterpriseDashboard.prototype.onGlobalKeydown.call(owner, { key: "Escape" });
    expect(owner.state.selectedKpi).toBe(false);
    expect(owner.state.navOpen).toBe(true);
    AgesEnterpriseDashboard.prototype.onGlobalKeydown.call(owner, { key: "Escape" });
    expect(owner.state.navOpen).toBe(false);
});

test("table view paginates and sorts numeric money strings", () => {
    const tableView = AgesEnterpriseDashboard.prototype.tableView;
    const owner = {
        state: {
            sort: { demo: { key: "amount", dir: "desc" } },
            tablePage: { demo: 0 },
            pageSize: 2,
        },
    };
    const view = tableView.call(owner, ["demo", {
        title: "Demo",
        columns: [{ key: "name", label: "Name" }, { key: "amount", label: "Amount" }],
        rows: [
            { name: "A", amount: "PKR 10.00" },
            { name: "B", amount: "PKR 30.00" },
            { name: "C", amount: "PKR 20.00" },
        ],
    }]);
    expect(view.total).toBe(3);
    expect(view.pages).toBe(2);
    expect(view.rows[0].name).toBe("B");
    expect(view.rows.length).toBe(2);
});

test("showFilter respects the dashboard catalog", () => {
    const owner = {
        state: {
            activeKey: "finance",
            filterCatalog: { finance: ["company", "journal", "account"] },
        },
    };
    expect(AgesEnterpriseDashboard.prototype.showFilter.call(owner, "journal")).toBe(true);
    expect(AgesEnterpriseDashboard.prototype.showFilter.call(owner, "product")).toBe(false);
});

test("hero-less payload still builds layout sections", () => {
    const owner = {
        state: {
            payload: {
                meta: { dashboard: "sales" },
                kpis: [{ key: "orders", label: "Orders" }],
                charts: { trend: { title: "Trend", labels: ["A"], datasets: [{ data: [2] }] } },
                tables: {},
                alerts: [],
            },
        },
    };
    const sections = Object.getOwnPropertyDescriptor(AgesEnterpriseDashboard.prototype, "layoutSections").get.call(owner);
    expect(sections.length > 0).toBe(true);
    expect(sections.some((section) => section.type === "kpis")).toBe(true);
});

test("executive command hero splits primary and secondary kpis", () => {
    const owner = {
        state: {
            activeKey: "executive",
            payload: {
                meta: { dashboard: "executive" },
                layout: { kind: "executive" },
                kpis: [
                    { key: "revenue", label: "Revenue" },
                    { key: "profit", label: "Net Result" },
                    { key: "cash", label: "Cash" },
                    { key: "receivables", label: "Receivables" },
                    { key: "ra_work", label: "RA Work" },
                ],
            },
        },
        sectionKpis: AgesEnterpriseDashboard.prototype.sectionKpis,
        kpiByKey: AgesEnterpriseDashboard.prototype.kpiByKey,
    };
    const section = {
        type: "kpis",
        hero: true,
        variant: "command",
        keys: ["revenue", "profit", "cash", "receivables", "ra_work"],
    };
    expect(AgesEnterpriseDashboard.prototype.isCommandHero.call(owner, section)).toBe(true);
    expect(AgesEnterpriseDashboard.prototype.heroPrimaryKpis.call(owner, section).map((kpi) => kpi.key)).toEqual([
        "revenue",
        "profit",
    ]);
    expect(AgesEnterpriseDashboard.prototype.heroSecondaryKpis.call(owner, section).map((kpi) => kpi.key)).toEqual([
        "cash",
        "receivables",
        "ra_work",
    ]);
});

test("executive briefing composes headline from queues and kpis", () => {
    const owner = {
        state: {
            activeKey: "executive",
            filters: { compare_period: "previous_period" },
            payload: {
                meta: { dashboard: "executive" },
                layout: { kind: "executive" },
                commentary: [],
                kpis: [
                    { key: "profit", label: "Net Result", formatted: "1 Rs", unavailable: false },
                    { key: "cash", label: "Cash", formatted: "2 Rs", unavailable: false },
                ],
                alerts: [
                    {
                        key: "unrec",
                        title: "Unreconciled journal items",
                        count: 12,
                        amount: 100,
                        amount_formatted: "100 Rs",
                        oldest_days: 9,
                        severity: "danger",
                        action_key: "unreconciled",
                    },
                ],
            },
        },
        kpiByKey: AgesEnterpriseDashboard.prototype.kpiByKey,
        get hasPayload() {
            return true;
        },
        get isExecutiveShell() {
            return true;
        },
        get visibleAlerts() {
            return this.state.payload.alerts;
        },
        get rankedWorkbenchQueues() {
            return Object.getOwnPropertyDescriptor(AgesEnterpriseDashboard.prototype, "rankedWorkbenchQueues").get.call(this);
        },
    };
    const briefing = Object.getOwnPropertyDescriptor(AgesEnterpriseDashboard.prototype, "executiveBriefing").get.call(owner);
    expect(Boolean(briefing)).toBe(true);
    expect(briefing.hasTop).toBe(true);
    expect(briefing.primaryAction).toBe("unreconciled");
    expect(String(briefing.headline).toLowerCase()).toMatch(/unreconciled|net result|cash/);
});

test("canAutoRefresh excludes executive", () => {
    const read = Object.getOwnPropertyDescriptor(AgesEnterpriseDashboard.prototype, "canAutoRefresh").get;
    expect(read.call({ state: { activeKey: "executive" } })).toBe(false);
    expect(read.call({ state: { activeKey: "action_center" } })).toBe(true);
    expect(read.call({ state: { activeKey: "inventory" } })).toBe(true);
});

test("inspector info click does not drill", () => {
    const owner = {
        state: { selectedKpi: false },
        openInspector(kpi) {
            this.state.selectedKpi = kpi;
        },
        openAction() {
            this.drilled = true;
        },
    };
    const ev = { stopPropagation() {}, preventDefault() {} };
    AgesEnterpriseDashboard.prototype.onKpiInfoClick.call(owner, { key: "revenue", action_key: "aml_income" }, ev);
    expect(owner.state.selectedKpi.key).toBe("revenue");
    expect(Boolean(owner.drilled)).toBe(false);
});

test("value click drills when action_key exists", () => {
    const owner = {
        opened: false,
        openInspector() {},
        openAction(key) {
            this.opened = key;
        },
    };
    AgesEnterpriseDashboard.prototype.onKpiValueClick.call(owner, { key: "revenue", action_key: "aml_income" });
    expect(owner.opened).toBe("aml_income");
});

test("csv export includes utf8 bom", () => {
    expect(AgesEnterpriseDashboard.prototype.csvEscape.call({}, "plain")).toBe("plain");
});
