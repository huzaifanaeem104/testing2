/** @odoo-module **/

import { DashboardKanbanRenderer } from "@account/views/account_dashboard_kanban/account_dashboard_kanban_renderer";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

patch(DashboardKanbanRenderer.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.overviewKpis = useState({
            loaded: false,
            gross_margin: "",
            revenue: "",
            net_margin: "",
            expenses: "",
            unpaid_customers: "",
            unpaid_suppliers: "",
            cash_in: "",
            cash_out: "",
        });
        onWillStart(async () => {
            try {
                const kpis = await this.orm.call("account.journal", "ages_get_overview_kpis", []);
                Object.assign(this.overviewKpis, kpis, { loaded: true });
            } catch {
                this.overviewKpis.loaded = true;
            }
        });
    },

    async openOverviewKpi(kpi, ev) {
        ev?.stopPropagation();
        ev?.preventDefault();
        const action = await this.orm.call("account.journal", "ages_open_overview_kpi", [kpi]);
        if (action?.type) {
            this.actionService.doAction(action);
        }
    },
});
