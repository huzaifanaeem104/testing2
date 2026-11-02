/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ListController } from "@web/views/list/list_controller";

function hideEl(el) {
    if (!el || el.dataset.buttonAccessHidden === "1") {
        return;
    }
    el.style.setProperty("display", "none", "important");
    el.setAttribute("aria-hidden", "true");
    el.dataset.buttonAccessHidden = "1";
}

function actionRoots() {
    return document.querySelectorAll(
        ".o_action, .o-dropdown--menu, .o-overlay-container, .modal .modal-content"
    );
}

function queryInActions(selector) {
    const matches = [];
    for (const root of actionRoots()) {
        root.querySelectorAll(selector).forEach((el) => matches.push(el));
    }
    return matches;
}

function applyFallback(buttonAccess) {
    const model = buttonAccess.getActiveModel();
    const rules = buttonAccess.rulesForModel(model);
    if (!rules.length) {
        return;
    }
    for (const rule of rules) {
        switch (rule.type) {
            case "create":
                queryInActions(
                    ".o_list_button_add, .o_form_button_create, .o-kanban-button-new"
                ).forEach(hideEl);
                break;
            case "delete":
                queryInActions(".o_list_record_remove").forEach(hideEl);
                break;
            case "import":
                queryInActions(".o_button_import, .o_import_button").forEach(hideEl);
                break;
            case "export":
                queryInActions(".o_list_export_xlsx").forEach(hideEl);
                break;
            default: {
                if (!rule.name) {
                    break;
                }
                for (const el of queryInActions("button[name], a[name]")) {
                    if (el.getAttribute("name") === rule.name) {
                        hideEl(el);
                    }
                }
                break;
            }
        }
    }
}

function patchStaticMenu(Controller) {
    patch(Controller.prototype, {
        setup() {
            super.setup(...arguments);
            const ba = this.env.services.button_access;
            if (ba && this.props.resModel) {
                ba.setActiveModel(this.props.resModel);
            }
        },
        getStaticActionMenuItems() {
            const items = super.getStaticActionMenuItems(...arguments);
            const ba = this.env.services.button_access;
            if (!ba) {
                return items;
            }
            const model = this.props.resModel;
            const disable = (key) => {
                if (items[key]) {
                    items[key].isAvailable = () => false;
                }
            };
            if (ba.hasType(model, "export")) {
                disable("export");
            }
            if (
                ba.hasType(model, "object", "action_archive") ||
                ba.hasType(model, "object", "toggle_active")
            ) {
                disable("archive");
            }
            if (
                ba.hasType(model, "object", "action_unarchive") ||
                ba.hasType(model, "object", "toggle_active")
            ) {
                disable("unarchive");
            }
            if (ba.hasType(model, "duplicate")) {
                disable("duplicate");
            }
            if (ba.hasType(model, "delete")) {
                disable("delete");
            }
            return items;
        },
    });
}

export const buttonHiderService = {
    dependencies: ["button_access"],
    start(env, { button_access }) {
        patchStaticMenu(ListController);
        patchStaticMenu(FormController);
        patch(KanbanController.prototype, {
            setup() {
                super.setup(...arguments);
                if (this.props.resModel) {
                    button_access.setActiveModel(this.props.resModel);
                }
            },
        });

        let timer = null;
        const run = () => applyFallback(button_access);
        const scheduleRun = () => {
            if (timer) {
                return;
            }
            timer = setTimeout(() => {
                timer = null;
                run();
            }, 80);
        };

        const observer = new MutationObserver(scheduleRun);
        const target = document.querySelector(".o_action_manager") || document.body;
        observer.observe(target, { childList: true, subtree: true });

        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () => {
            button_access.maybeReload();
            scheduleRun();
        });
        setTimeout(scheduleRun, 300);
        return {};
    },
};

registry.category("services").add("button_hider", buttonHiderService);
