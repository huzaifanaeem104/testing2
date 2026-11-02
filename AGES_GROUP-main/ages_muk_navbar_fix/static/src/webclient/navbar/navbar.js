/** @odoo-module **/

import { patch } from '@web/core/utils/patch';
import { useBus } from '@web/core/utils/hooks';

import { NavBar } from '@web/webclient/navbar/navbar';

function isMukAppsMenuOpen(component) {
    return Boolean(component.mukAppsMenuOpen);
}

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.mukAppsMenuOpen = false;

        useBus(this.env.bus, 'MUK:APPS-MENU-TOGGLED', ({ detail: isOpen }) => {
            this.mukAppsMenuOpen = isOpen === true;
            this.render();
        });

        useBus(this.env.bus, 'MENUS:APP-CHANGED', () => {
            this.mukAppsMenuOpen = false;
            this.render();
        });
    },

    get isNavbarInHomeMenu() {
        return isMukAppsMenuOpen(this);
    },

    get currentApp() {
        if (isMukAppsMenuOpen(this)) {
            return;
        }
        return this.menuService.getCurrentApp();
    },

    get currentAppSections() {
        if (isMukAppsMenuOpen(this)) {
            return [];
        }
        const currentApp = this.menuService.getCurrentApp();
        return (
            (currentApp && this.menuService.getMenuAsTree(currentApp.id).childrenTree) ||
            []
        );
    },

    async adapt() {
        if (isMukAppsMenuOpen(this)) {
            return;
        }
        return super.adapt(...arguments);
    },
});
