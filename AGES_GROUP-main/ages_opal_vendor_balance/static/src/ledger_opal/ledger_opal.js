/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AgesPartnerLedgerReport } from "@ages_custom_reports/partner_ledger_report/partner_ledger_report";
import { AgesGeneralLedgerReport } from "@ages_custom_reports/general_ledger_report/general_ledger_report";

function patchLedgerOpal(Report) {
    patch(Report.prototype, {
        setup() {
            super.setup(...arguments);
            this.state.showOpalBalance = false;
        },

        _loadFilters(filters) {
            super._loadFilters(filters);
            if (filters && Object.prototype.hasOwnProperty.call(filters, "show_opal_balance")) {
                this.state.showOpalBalance = !!filters.show_opal_balance;
            }
        },

        _filterPayload() {
            return {
                ...super._filterPayload(),
                show_opal_balance: !!this.state.showOpalBalance,
            };
        },

        onShowOpalBalanceChange(ev) {
            this.state.showOpalBalance = ev.target.checked;
            this.state.partnerDetails = {};
            this.refreshReport();
        },

        rowClass(line) {
            const cls = super.rowClass(line);
            return line.line_type === "opal" ? `${cls} o_ages_opal_ledger_row`.trim() : cls;
        },
    });
}

patchLedgerOpal(AgesPartnerLedgerReport);
patchLedgerOpal(AgesGeneralLedgerReport);
