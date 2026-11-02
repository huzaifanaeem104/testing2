/** @odoo-module **/

import { registry } from "@web/core/registry";
import { WorksShell } from "./works_shell";

export class WorksContracts extends WorksShell {
    static screenKey = "contracts";
}

registry.category("actions").add("ages_works_desk.contracts", WorksContracts);
