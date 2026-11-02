/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

export class PayrollDashboardPayslipBatch extends Component {
    static template = "ages_hr_payroll.PayslipBatch";
    static props = ["batches"];

    setup() {
        this.actionService = useService("action");
    }

    onClickTitle() {
        this.actionService.doAction("ages_hr_payroll.action_hr_payslip_run_tree");
    }

    getColorFromState(state) {
        const colorMap = {
            New: "text-bg-secondary",
            Confirmed: "text-bg-success",
            Done: "text-bg-primary",
            Paid: "text-bg-warning",
        };
        return colorMap[state] || "text-bg-primary";
    }

    onClickLine(batchID) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Employee Payslips"),
            res_model: "hr.payslip.run",
            res_id: batchID,
            views: [[false, "form"]],
        });
    }
}
