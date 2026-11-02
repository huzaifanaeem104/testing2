/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { session } from "@web/session";

function isExcepted(exceptions, model, rule) {
    return (exceptions || []).some((exc) => {
        if (exc.type !== rule.type) {
            return false;
        }
        if (exc.model && exc.model !== model) {
            return false;
        }
        if (exc.name && exc.name !== (rule.name || "")) {
            return false;
        }
        return true;
    });
}

function indexRules(rules, exceptions) {
    const byModel = {};
    const globalRules = [];
    for (const r of rules || []) {
        if (!r.model) {
            globalRules.push(r);
            continue;
        }
        if (!byModel[r.model]) {
            byModel[r.model] = [];
        }
        byModel[r.model].push(r);
    }
    return {
        rules: rules || [],
        exceptions: exceptions || [],
        byModel,
        globalRules,
        hasRules: Boolean((rules || []).length),
    };
}

export const buttonAccessService = {
    dependencies: [],
    start() {
        const state = indexRules(
            session.button_access_rules || [],
            session.button_access_exceptions || []
        );
        let activeModel = null;
        let lastReload = 0;

        const applyIndex = (indexed) => {
            state.rules = indexed.rules;
            state.exceptions = indexed.exceptions || state.exceptions || [];
            state.byModel = indexed.byModel;
            state.globalRules = indexed.globalRules;
            state.hasRules = indexed.hasRules;
        };

        const api = {
            get rules() {
                return state.rules;
            },
            get hasRules() {
                return state.hasRules;
            },
            get globalRules() {
                return state.globalRules;
            },
            getActiveModel() {
                return activeModel;
            },
            setActiveModel(model) {
                if (model) {
                    activeModel = model;
                }
            },
            rulesForModel(model) {
                const specific = (model && state.byModel[model]) || [];
                const combined = state.globalRules.length
                    ? specific.concat(state.globalRules)
                    : specific;
                return combined.filter((rule) => !isExcepted(state.exceptions, model, rule));
            },
            hasType(model, type, name) {
                const rules = api.rulesForModel(model);
                if (name) {
                    return rules.some(
                        (r) => r.type === type && (!r.name || r.name === name)
                    );
                }
                return rules.some((r) => r.type === type);
            },
            async reload() {
                try {
                    const fresh = await rpc("/button_access_manager/rules", {});
                    applyIndex(indexRules(fresh || [], state.exceptions));
                    lastReload = Date.now();
                } catch (e) {
                    console.warn("button_access_manager: could not reload button rules", e);
                }
            },
            maybeReload() {
                if (Date.now() - lastReload < 60000) {
                    return;
                }
                return api.reload();
            },
        };
        return api;
    },
};

registry.category("services").add("button_access", buttonAccessService);
