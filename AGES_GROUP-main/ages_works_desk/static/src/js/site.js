/** @odoo-module **/

import { registry } from "@web/core/registry";
import { WorksShell } from "./works_shell";

export class WorksSite extends WorksShell {
    static screenKey = "site";
}

registry.category("actions").add("ages_works_desk.site", WorksSite);
