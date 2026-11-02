/** @odoo-module **/

import { registry } from "@web/core/registry";
import { WorksShell } from "./works_shell";

export class WorksSpend extends WorksShell {
    static screenKey = "spend";
}

registry.category("actions").add("ages_works_desk.spend", WorksSpend);
