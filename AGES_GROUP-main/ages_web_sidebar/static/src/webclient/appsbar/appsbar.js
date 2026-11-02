/** @odoo-module **/

import { patch } from '@web/core/utils/patch';
import { useState } from '@odoo/owl';
import { useBus } from '@web/core/utils/hooks';

import { AppsBar } from '@muk_web_appsbar/webclient/appsbar/appsbar';

patch(AppsBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.sidebarState = useState({
            hovered: false,
            collapsed: this._shouldCollapseSidebar(),
        });

        const syncCollapsed = () => {
            this.sidebarState.collapsed = this._shouldCollapseSidebar();
            if (!this.sidebarState.collapsed) {
                this.sidebarState.hovered = false;
            }
        };

        useBus(this.env.bus, 'MENUS:APP-CHANGED', syncCollapsed);
        useBus(this.env.bus, 'ACTION_MANAGER:UI-UPDATED', (mode) => {
            if (mode !== 'new') {
                syncCollapsed();
            }
        });
    },

    _shouldCollapseSidebar() {
        return !!this.appMenuService.getCurrentApp();
    },

    onSidebarMouseEnter() {
        if (this.sidebarState.collapsed) {
            this.sidebarState.hovered = true;
        }
    },

    onSidebarMouseLeave() {
        this.sidebarState.hovered = false;
    },

    get sidebarPanelClass() {
        return {
            mk_apps_sidebar_panel: true,
            mk_apps_sidebar_collapsed:
                this.sidebarState.collapsed && !this.sidebarState.hovered,
            mk_apps_sidebar_expanded: this.sidebarState.hovered,
        };
    },
});
