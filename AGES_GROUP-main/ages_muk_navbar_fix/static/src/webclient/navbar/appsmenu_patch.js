/** @odoo-module **/

import { patch } from '@web/core/utils/patch';
import { useEffect } from '@odoo/owl';

import { AppsMenu } from '@muk_web_theme/webclient/appsmenu/appsmenu';

patch(AppsMenu.prototype, {
    setup() {
        super.setup(...arguments);
        useEffect(
            (isOpen) => {
                this.env.bus.trigger('MUK:APPS-MENU-TOGGLED', isOpen);
            },
            () => [this.state.isOpen]
        );
    },
});
