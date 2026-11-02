/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

export class PayrollDashboardActionBox extends Component {
    static template = "ages_hr_payroll.ActionBox";
    static props = ["*"];

    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            warnings: [],
        });
        onWillStart(async () => {
            this.state.warnings = await this.orm.call("hr.payslip", "get_dashboard_warnings");
            this.state.loading = false;
        });
    }
}
