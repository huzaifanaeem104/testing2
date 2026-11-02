/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { session } from "@web/session";
import { user } from "@web/core/user";
import { browser } from "@web/core/browser/browser";
import { SessionTimeoutDialog } from "./session_timeout_dialog";

const CHECK_URL = "/ages_user_session_timeout/check";
const ACTIVITY_URL = "/ages_user_session_timeout/activity";
const LOGOUT_URL = "/web/session/logout";
const INTERACTION_EVENTS = [
    "mousedown",
    "keydown",
    "scroll",
    "touchstart",
    "input",
    "change",
    "click",
];

function payloadToConfig(payload) {
    if (!payload || payload.enabled === false || !user.userId) {
        return null;
    }
    const idleMs = Math.max(60, Number(payload.idle_seconds) || 900) * 1000;
    const warningMs = Math.min(
        Math.max(10, Number(payload.warning_seconds) || 60) * 1000,
        idleMs - 5000
    );
    return {
        idleMs,
        warningMs,
        remainingMs: Math.max(0, Number(payload.remaining_seconds) || 0) * 1000,
        sessionScope: payload.session_scope || `${user.userId}:${payload.session_identifier || ""}`,
    };
}

export const agesSessionTimeoutService = {
    dependencies: ["dialog"],
    start(env) {
        const dialog = env.services.dialog;
        let cfg = payloadToConfig(session.ages_session_timeout || {});
        let idleMs = cfg ? cfg.idleMs : 15 * 60 * 1000;
        let warningMs = cfg ? cfg.warningMs : 60 * 1000;
        let sessionScope = cfg ? cfg.sessionScope : "";
        let expiresAt = cfg ? Date.now() + (cfg.remainingMs || idleMs) : 0;
        let warningAt = expiresAt - warningMs;
        let idleTimer;
        let warningTimer;
        let checkTimer;
        let warningOpen = false;
        let lastActivitySync = 0;
        let listenersBound = false;
        let lastPointer = { x: 0, y: 0 };
        const syncEveryMs = 30 * 1000;
        let channel = null;

        const storageKey = () => `ages.session.timeout.${sessionScope}`;

        const persistExpiry = () => {
            if (!sessionScope) {
                return;
            }
            try {
                browser.localStorage.setItem(storageKey(), String(expiresAt));
            } catch (_error) {
                // Ignore private-mode storage errors.
            }
        };

        const readStoredExpiry = () => {
            if (!sessionScope) {
                return null;
            }
            try {
                const raw = browser.localStorage.getItem(storageKey());
                const parsed = parseInt(raw, 10);
                return Number.isFinite(parsed) ? parsed : null;
            } catch (_error) {
                return null;
            }
        };

        const logout = () => {
            try {
                browser.localStorage.removeItem(storageKey());
            } catch (_error) {
                // Ignore.
            }
            if (channel) {
                channel.postMessage({ type: "logout", scope: sessionScope });
            }
            browser.location.href = LOGOUT_URL;
        };

        const remainingMs = () => expiresAt - Date.now();

        const openWarning = () => {
            if (warningOpen || !cfg) {
                return;
            }
            const dialogService = env.services.dialog || dialog;
            if (!dialogService) {
                return;
            }
            warningOpen = true;
            const seconds = Math.max(1, Math.ceil(remainingMs() / 1000));
            dialogService.add(SessionTimeoutDialog, {
                remaining: seconds,
                idleMinutes: Math.max(1, Math.round(idleMs / 60000)),
                onStay: () => {
                    warningOpen = false;
                    markActivity({ forceSync: true });
                },
                onLogout: () => logout(),
            }, {
                onClose: () => {
                    warningOpen = false;
                },
            });
        };

        const scheduleTimers = () => {
            browser.clearTimeout(idleTimer);
            browser.clearTimeout(warningTimer);
            if (!cfg) {
                return;
            }
            const left = remainingMs();
            if (left <= 0) {
                logout();
                return;
            }
            const untilWarning = warningAt - Date.now();
            if (untilWarning <= 0) {
                openWarning();
            } else {
                warningTimer = browser.setTimeout(openWarning, untilWarning);
            }
            idleTimer = browser.setTimeout(logout, left);
        };

        const applyExpiry = (nextExpiresAt, { broadcast = true } = {}) => {
            if (!cfg) {
                return;
            }
            expiresAt = nextExpiresAt;
            warningAt = expiresAt - warningMs;
            persistExpiry();
            if (broadcast && channel) {
                channel.postMessage({ type: "activity", expiresAt, scope: sessionScope });
            }
            scheduleTimers();
        };

        const syncActivity = async ({ force = false } = {}) => {
            if (!cfg) {
                return;
            }
            const now = Date.now();
            if (!force && now - lastActivitySync < syncEveryMs) {
                return;
            }
            lastActivitySync = now;
            try {
                const result = await rpc(ACTIVITY_URL, {});
                applyServerPayload(result, { broadcast: true });
            } catch (_error) {
                // Keep the client timer if the network blips; the server still enforces.
            }
        };

        const markActivity = ({ forceSync = false } = {}) => {
            if (!cfg) {
                return;
            }
            applyExpiry(Date.now() + idleMs);
            syncActivity({ force: forceSync });
        };

        let debounceId;
        const onInteraction = () => {
            if (warningOpen) {
                return;
            }
            browser.clearTimeout(debounceId);
            debounceId = browser.setTimeout(() => markActivity(), 250);
        };

        const onMouseMove = (event) => {
            const dx = event.clientX - lastPointer.x;
            const dy = event.clientY - lastPointer.y;
            if ((dx * dx) + (dy * dy) < 400) {
                return;
            }
            lastPointer = { x: event.clientX, y: event.clientY };
            onInteraction();
        };

        const bindChannel = () => {
            if (channel || !sessionScope) {
                return;
            }
            try {
                channel = new BroadcastChannel(`ages-session-timeout:${sessionScope}`);
            } catch (_error) {
                channel = null;
                return;
            }
            channel.addEventListener("message", (event) => {
                const data = event.data || {};
                if (data.scope && data.scope !== sessionScope) {
                    return;
                }
                if (data.type === "logout") {
                    browser.location.href = LOGOUT_URL;
                }
                if (data.type === "activity" && data.expiresAt) {
                    applyExpiry(data.expiresAt, { broadcast: false });
                }
            });
        };

        const bindListeners = () => {
            if (listenersBound) {
                return;
            }
            listenersBound = true;
            INTERACTION_EVENTS.forEach((eventName) => {
                browser.addEventListener(eventName, onInteraction, { passive: true });
            });
            browser.addEventListener("mousemove", onMouseMove, { passive: true });
            document.addEventListener("visibilitychange", () => {
                if (!document.hidden) {
                    checkServer();
                }
            });
            browser.addEventListener("online", checkServer);
            browser.addEventListener("pageshow", checkServer);
        };

        const activate = (nextCfg) => {
            const wasEnabled = Boolean(cfg);
            cfg = nextCfg;
            idleMs = nextCfg.idleMs;
            warningMs = nextCfg.warningMs;
            sessionScope = nextCfg.sessionScope;
            bindChannel();
            bindListeners();
            if (!wasEnabled) {
                expiresAt = Date.now() + (nextCfg.remainingMs || idleMs);
                const stored = readStoredExpiry();
                if (stored && stored > Date.now() && stored < expiresAt) {
                    expiresAt = stored;
                }
                warningAt = expiresAt - warningMs;
                persistExpiry();
            }
            scheduleTimers();
        };

        const deactivate = () => {
            cfg = null;
            browser.clearTimeout(idleTimer);
            browser.clearTimeout(warningTimer);
            warningOpen = false;
        };

        const applyServerPayload = (result, { broadcast = false } = {}) => {
            if (!result) {
                return;
            }
            if (result.valid === false) {
                logout();
                return;
            }
            const nextCfg = payloadToConfig(result);
            if (!nextCfg) {
                deactivate();
                return;
            }
            if (!cfg || cfg.sessionScope !== nextCfg.sessionScope) {
                activate(nextCfg);
            } else {
                idleMs = nextCfg.idleMs;
                warningMs = nextCfg.warningMs;
            }
            if (result.remaining_seconds != null) {
                applyExpiry(Date.now() + result.remaining_seconds * 1000, { broadcast });
            } else {
                scheduleTimers();
            }
        };

        const checkServer = async () => {
            try {
                const result = await rpc(CHECK_URL, {});
                applyServerPayload(result, { broadcast: false });
            } catch (_error) {
                scheduleTimers();
            }
        };

        if (cfg) {
            activate(cfg);
        }
        checkTimer = browser.setInterval(checkServer, 15 * 1000);
        checkServer();

        return {
            enabled: Boolean(cfg),
            markActivity,
            cleanup() {
                INTERACTION_EVENTS.forEach((eventName) => {
                    browser.removeEventListener(eventName, onInteraction, { passive: true });
                });
                browser.removeEventListener("mousemove", onMouseMove, { passive: true });
                browser.clearTimeout(idleTimer);
                browser.clearTimeout(warningTimer);
                browser.clearTimeout(debounceId);
                browser.clearInterval(checkTimer);
                if (channel) {
                    channel.close();
                }
            },
        };
    },
};

registry.category("services").add("ages_session_timeout", agesSessionTimeoutService);
