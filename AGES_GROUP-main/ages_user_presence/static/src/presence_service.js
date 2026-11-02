/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { session } from "@web/session";
import { user } from "@web/core/user";
import { browser } from "@web/core/browser/browser";

const HEARTBEAT_URL = "/ages_user_presence/heartbeat";
const LOGOUT_URL = "/web/session/logout";
const CHANNEL_NAME = "ages-user-presence";
const RANK = { active: 3, idle: 2, background: 1 };
const INTERACTION_EVENTS = [
    "mousemove",
    "mousedown",
    "keydown",
    "scroll",
    "touchstart",
    "touchmove",
    "input",
    "change",
    "wheel",
    "click",
];

function readConfig() {
    const config = session.ages_user_presence || {};
    const uid = user.userId || session.uid;
    if (!config.enabled || !uid) {
        return null;
    }
    return {
        heartbeatMs: Math.max(15, Number(config.heartbeat_seconds) || 30) * 1000,
        idleMs: Math.max(60, Number(config.idle_seconds) || 300) * 1000,
        sessionIdentifier: config.session_identifier || "",
    };
}

function localPresence({ visible, focused, idle }) {
    if (!visible) {
        return "background";
    }
    if (idle) {
        return "idle";
    }
    if (!focused) {
        return "background";
    }
    return "active";
}

function bestOf(states) {
    let best = states[0];
    for (const state of states) {
        if (!best || RANK[state.presence] > RANK[best.presence]) {
            best = state;
            continue;
        }
        if (RANK[state.presence] === RANK[best.presence] && state.lastInteraction > best.lastInteraction) {
            best = state;
        }
    }
    return best;
}

export const agesUserPresenceService = {
    dependencies: ["bus_service"],
    start(env) {
        const initial = readConfig();
        if (!initial) {
            return { enabled: false };
        }
        const busService = env.services.bus_service;
        const tabId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const peers = new Map();
        let lastInteraction = Date.now();
        let lastHeartbeatAt = 0;
        let lastSentPresence = null;
        let heartbeatTimer;
        let idleTimer;
        let debounceId;
        let sending = false;

        const channel = (() => {
            try {
                return new BroadcastChannel(CHANNEL_NAME);
            } catch (_error) {
                return null;
            }
        })();

        const pageVisible = () => {
            try {
                return document.visibilityState !== "hidden";
            } catch (_error) {
                return true;
            }
        };

        const pageFocused = () => {
            try {
                return typeof document.hasFocus === "function" ? document.hasFocus() : true;
            } catch (_error) {
                return true;
            }
        };

        const localState = () => {
            const visible = pageVisible();
            const focused = visible && pageFocused();
            const idle = Date.now() - lastInteraction >= initial.idleMs;
            const presence = localPresence({ visible, focused, idle });
            return {
                tabId,
                presence,
                visibility: visible ? "visible" : "hidden",
                focused,
                lastInteraction,
                ts: Date.now(),
            };
        };

        const prunePeers = () => {
            const staleBefore = Date.now() - initial.heartbeatMs * 2;
            for (const [id, peer] of peers) {
                if (!peer.ts || peer.ts < staleBefore) {
                    peers.delete(id);
                }
            }
        };

        const aggregatedState = () => {
            const local = localState();
            if (channel) {
                channel.postMessage({ type: "state", ...local });
            }
            prunePeers();
            const states = [local, ...peers.values()];
            const best = bestOf(states);
            return {
                presence: best.presence,
                visibility: best.visibility,
                focused: best.focused,
                lastInteraction: Math.max(...states.map((item) => item.lastInteraction || 0)),
            };
        };

        const sendHeartbeat = async ({ force = false } = {}) => {
            if (sending) {
                return;
            }
            const now = Date.now();
            const minGap = force ? 2000 : initial.heartbeatMs;
            if (!force && now - lastHeartbeatAt < minGap) {
                return;
            }
            const state = aggregatedState();
            const interacted = state.lastInteraction > lastHeartbeatAt;
            if (
                !force
                && state.presence === lastSentPresence
                && !interacted
                && now - lastHeartbeatAt < initial.heartbeatMs
            ) {
                return;
            }
            sending = true;
            lastHeartbeatAt = now;
            lastSentPresence = state.presence;
            try {
                await rpc(HEARTBEAT_URL, {
                    presence: state.presence,
                    visibility: state.visibility,
                    focused: Boolean(state.focused),
                    interacted,
                });
            } catch (_error) {
                // Keep going; inactivity cron handles missing heartbeats.
            } finally {
                sending = false;
            }
        };

        const scheduleIdleCheck = () => {
            browser.clearTimeout(idleTimer);
            const remaining = initial.idleMs - (Date.now() - lastInteraction);
            if (remaining <= 0) {
                if (pageVisible() && lastSentPresence !== "idle") {
                    sendHeartbeat({ force: true });
                }
                return;
            }
            idleTimer = browser.setTimeout(() => {
                if (pageVisible()) {
                    sendHeartbeat({ force: true });
                }
            }, remaining + 25);
        };

        const onInteraction = () => {
            lastInteraction = Date.now();
            browser.clearTimeout(debounceId);
            debounceId = browser.setTimeout(() => {
                if (lastSentPresence === "idle") {
                    sendHeartbeat({ force: true });
                }
                scheduleIdleCheck();
            }, 250);
        };

        const onVisibilityOrFocus = () => {
            sendHeartbeat({ force: true });
            scheduleIdleCheck();
        };

        INTERACTION_EVENTS.forEach((eventName) => {
            browser.addEventListener(eventName, onInteraction, { passive: true });
        });
        document.addEventListener("visibilitychange", onVisibilityOrFocus);
        browser.addEventListener("focus", onVisibilityOrFocus);
        browser.addEventListener("blur", onVisibilityOrFocus);

        if (channel) {
            channel.addEventListener("message", (event) => {
                const data = event.data || {};
                if (data.type === "bye") {
                    peers.delete(data.tabId);
                    return;
                }
                if (data.type === "state" && data.tabId && data.tabId !== tabId) {
                    peers.set(data.tabId, data);
                }
            });
        }

        browser.addEventListener("pagehide", () => {
            if (channel) {
                channel.postMessage({ type: "bye", tabId });
            }
        });

        if (busService) {
            busService.subscribe("ages.user.presence/force_logout", (payload) => {
                if (payload && payload.session_identifier && payload.session_identifier === initial.sessionIdentifier) {
                    browser.location.href = LOGOUT_URL;
                }
            });
        }

        heartbeatTimer = browser.setInterval(() => sendHeartbeat({ force: false }), initial.heartbeatMs);
        scheduleIdleCheck();
        sendHeartbeat({ force: true });

        return {
            enabled: true,
            cleanup() {
                INTERACTION_EVENTS.forEach((eventName) => {
                    browser.removeEventListener(eventName, onInteraction, { passive: true });
                });
                document.removeEventListener("visibilitychange", onVisibilityOrFocus);
                browser.removeEventListener("focus", onVisibilityOrFocus);
                browser.removeEventListener("blur", onVisibilityOrFocus);
                browser.clearTimeout(idleTimer);
                browser.clearTimeout(debounceId);
                browser.clearInterval(heartbeatTimer);
                if (channel) {
                    channel.close();
                }
            },
        };
    },
};

registry.category("services").add("ages_user_presence", agesUserPresenceService);
