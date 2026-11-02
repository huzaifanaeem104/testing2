/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

import { PayrollDashboardActionBox } from "@ages_hr_payroll/components/dashboard/action_box/action_box";
import { PayrollDashboardPayslipBatch } from "@ages_hr_payroll/components/dashboard/payslip_batch/payslip_batch";
import { PayrollDashboardTodo } from "@ages_hr_payroll/components/dashboard/todo_list/todo_list";
import { PayrollDashboardStats } from "@ages_hr_payroll/components/dashboard/payroll_stats/payroll_stats";

class PayrollDashboardComponent extends Component {
    static template = "ages_hr_payroll.Dashboard";
    static components = {
        PayrollDashboardActionBox,
        PayrollDashboardPayslipBatch,
        PayrollDashboardTodo,
        PayrollDashboardStats,
    };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        onWillStart(async () => {
            this.dashboardData = await this.orm.call("hr.payslip", "get_payroll_dashboard_data", []);
        });
    }
}

registry.category("actions").add("ages_hr_payroll_dashboard", PayrollDashboardComponent);

export default PayrollDashboardComponent;
