/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { browser } from "@web/core/browser/browser";
import { onMounted, onWillUnmount, useState } from "@odoo/owl";

export class PresenceListController extends listView.Controller {
    static template = "ages_user_presence.PresenceListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.busService = useService("bus_service");
        this.summary = useState({
            users_online: 0,
            active_sessions: 0,
            active: 0,
            background: 0,
            idle: 0,
            inactive: 0,
        });
        this._presenceReloadTimer = null;
        this._presencePollTimer = null;
        this._onPresenceUpdated = this._onPresenceUpdated.bind(this);
        onMounted(() => {
            this.busService.subscribe("ages.user.presence/updated", this._onPresenceUpdated);
            this._loadSummary();
            this._presencePollTimer = browser.setInterval(() => {
                this._softReload();
            }, 30000);
        });
        onWillUnmount(() => {
            this.busService.unsubscribe("ages.user.presence/updated", this._onPresenceUpdated);
            browser.clearTimeout(this._presenceReloadTimer);
            browser.clearInterval(this._presencePollTimer);
        });
    }

    _onPresenceUpdated() {
        browser.clearTimeout(this._presenceReloadTimer);
        this._presenceReloadTimer = browser.setTimeout(() => this._softReload(), 750);
    }

    async _softReload() {
        try {
            await this.model.load();
            await this._loadSummary();
        } catch (_error) {
            // View may already be destroyed.
        }
    }

    async _loadSummary() {
        try {
            const summary = await this.orm.call("ages.user.session", "get_online_summary", []);
            Object.assign(this.summary, summary || {});
        } catch (_error) {
            // Keep the last known counts.
        }
    }
}

registry.category("views").add("ages_presence_list", {
    ...listView,
    Controller: PresenceListController,
});
