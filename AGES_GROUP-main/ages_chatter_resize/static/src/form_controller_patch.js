import { useEffect, useState } from "@odoo/owl";

import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    setup() {
        super.setup();
        this.agesChatter = useState(useService("ages.chatter_resize"));
        useEffect(
            () => {
                const el = this.rootRef.el;
                if (!el) {
                    return;
                }
                el.style.setProperty("--ages-chatter-width", `${this.agesChatter.width}px`);
                el.classList.toggle("o_ages_chatter_hidden", this.agesChatter.hidden);
            },
            () => [this.agesChatter.width, this.agesChatter.hidden]
        );
    },
    agesShowChatter() {
        this.agesChatter.setHidden(false);
    },
});
