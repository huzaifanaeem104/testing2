/** @odoo-module **/

import { registry } from "@web/core/registry";
import { WorksShell } from "./works_shell";

export class WorksToday extends WorksShell {
    static screenKey = "today";
}

registry.category("actions").add("ages_works_desk.today", WorksToday);
