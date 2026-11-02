/** @odoo-module **/

import { registry } from "@web/core/registry";
import { WorksShell } from "./works_shell";

export class WorksBooks extends WorksShell {
    static screenKey = "books";
}

registry.category("actions").add("ages_works_desk.books", WorksBooks);
