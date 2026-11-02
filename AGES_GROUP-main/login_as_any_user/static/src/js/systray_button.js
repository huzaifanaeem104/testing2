/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { session } from "@web/session";
import { Component } from "@odoo/owl";

export class UserSwitchWidget extends Component {
    setup() {
        super.setup();
        this.action = useService("action");
    }

    async _onClick() {
        const result = await rpc("/switch/user", {});
        if (result && result.can_switch) {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: "Switch User",
                res_model: "user.selection",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
            });
            return;
        }
        if (result && result.is_impersonated) {
            await rpc("/switch/admin", {});
            location.reload();
        }
    }
}

UserSwitchWidget.template = "UserSwitchSystray";

registry.category("systray").add("UserSwitchSystray", {
    Component: UserSwitchWidget,
    isDisplayed: () => Boolean(session.login_as_any_user),
});
