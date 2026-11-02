import { useState } from "@odoo/owl";

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { browser } from "@web/core/browser/browser";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.agesChatter = useState(useService("ages.chatter_resize"));
    },
    agesHideChatter() {
        this.agesChatter.setHidden(true);
    },
    agesOnResizeStart(ev) {
        if (ev.button !== undefined && ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const startX = ev.touches ? ev.touches[0].clientX : ev.clientX;
        const startWidth = this.agesChatter.width;
        const formEl = this.rootRef.el?.closest(".o_form_view");
        const maxWidth = formEl ? Math.floor(formEl.clientWidth * 0.7) : 900;

        const onMove = (moveEv) => {
            const clientX = moveEv.touches ? moveEv.touches[0].clientX : moveEv.clientX;
            const next = startWidth + (startX - clientX);
            this.agesChatter.setWidth(Math.min(maxWidth, Math.max(this.agesChatter.minWidth, next)));
        };
        const onUp = () => {
            browser.removeEventListener("mousemove", onMove);
            browser.removeEventListener("mouseup", onUp);
            browser.removeEventListener("touchmove", onMove);
            browser.removeEventListener("touchend", onUp);
            document.body.classList.remove("o_ages_chatter_resizing");
        };
        document.body.classList.add("o_ages_chatter_resizing");
        browser.addEventListener("mousemove", onMove);
        browser.addEventListener("mouseup", onUp);
        browser.addEventListener("touchmove", onMove, { passive: false });
        browser.addEventListener("touchend", onUp);
    },
    agesOnResizeReset() {
        this.agesChatter.resetWidth();
    },
});
