/** @odoo-module **/

import { Component, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class SessionTimeoutDialog extends Component {
    static template = "ages_user_session_timeout.SessionTimeoutDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        remaining: { type: Number, optional: true },
        idleMinutes: { type: Number, optional: true },
        onStay: Function,
        onLogout: Function,
    };

    setup() {
        this.state = useState({ remaining: Math.max(1, this.props.remaining || 1) });
        this._interval = setInterval(() => {
            this.state.remaining -= 1;
            if (this.state.remaining <= 0) {
                this._clear();
                this.props.onLogout();
            }
        }, 1000);
        onWillUnmount(() => this._clear());
    }

    _clear() {
        if (this._interval) {
            clearInterval(this._interval);
            this._interval = null;
        }
    }

    get title() {
        return _t("Session timeout warning");
    }

    get countdownLabel() {
        const total = Math.max(0, this.state.remaining);
        const minutes = Math.floor(total / 60);
        const seconds = total % 60;
        if (minutes > 0) {
            return _t("%s min %s sec", String(minutes), String(seconds).padStart(2, "0"));
        }
        return _t("%s seconds", String(seconds));
    }

    stayLoggedIn() {
        this._clear();
        this.props.onStay();
        this.props.close();
    }

    logoutNow() {
        this._clear();
        this.props.onLogout();
    }
}
