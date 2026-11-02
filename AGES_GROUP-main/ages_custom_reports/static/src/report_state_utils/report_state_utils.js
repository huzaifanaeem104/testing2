/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";

const STORAGE_PREFIX = "ages.report.filters.v1";

function _normalizeOptions(options) {
    if (typeof options === "string") {
        return { detailCacheField: options };
    }
    return options || {};
}

function _currentUserId() {
    return session.uid || session.user_id || 0;
}

function _reportKey(props, options = {}) {
    return options.reportKey || props.action?.tag || String(props.action?.id || "report");
}

function _storageKey(reportKey) {
    return `${STORAGE_PREFIX}:${_currentUserId()}:${reportKey}`;
}

function readStoredFilters(storageKey) {
    try {
        const raw = browser.localStorage.getItem(storageKey);
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
        return null;
    }
}

function writeStoredFilters(storageKey, payload) {
    try {
        browser.localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch {
        // Quota or private mode — keep the report usable.
    }
}

/**
 * Read UI state restored from the action breadcrumb stack.
 */
export function readSavedReportUiState(props, options = {}) {
    const { filterFields = [] } = _normalizeOptions(options);
    const saved = props.state || {};
    const result = {
        expandedIds: saved.expandedIds ? { ...saved.expandedIds } : {},
        detailCache: saved.detailCache ? { ...saved.detailCache } : {},
        unfoldAll: saved.unfoldAll,
        wizardId: saved.wizardId ?? props.action?.params?.wizard_id ?? null,
    };
    for (const field of filterFields) {
        if (field in saved) {
            result[field] = saved[field];
        }
    }
    return result;
}

/**
 * Export UI state for Odoo action persistence (breadcrumb back navigation).
 */
export function buildReportLocalState(state, options = {}) {
    const {
        detailCacheField = null,
        filterFields = [],
        includeWizardId = true,
    } = _normalizeOptions(options);

    const localState = {
        expandedIds: { ...state.expandedIds },
        unfoldAll: state.unfoldAll,
    };
    if (includeWizardId && state.wizardId) {
        localState.wizardId = state.wizardId;
    }
    if (detailCacheField && state[detailCacheField]) {
        localState.detailCache = { ...state[detailCacheField] };
    }
    for (const field of filterFields) {
        localState[field] = cloneFilterValue(state[field]);
    }
    return localState;
}

const FILTER_SERVER_TO_STATE = {
    partner_ids: "partnerIds",
    partner_names: "partnerNames",
    partner_id: "partnerId",
    partner_name: "partnerName",
    partner_category_ids: "partnerCategoryIds",
    account_ids: "accountIds",
    account_names: "accountNames",
    account_id: "accountId",
    account_name: "accountName",
    journal_ids: "journalIds",
    journal_names: "journalNames",
    analytic_account_id: "analyticAccountId",
    analytic_account_name: "analyticAccountName",
    sub_company_id: "subCompanyId",
    sub_company_name: "subCompanyName",
    sub_company_ids: "subCompanyIds",
    sub_company_names: "subCompanyNames",
    project_ids: "projectIds",
    project_names: "projectNames",
    contract_ids: "contractIds",
    contract_names: "contractNames",
};

/**
 * Drop deleted relational records from the in-memory filter state.
 */
export function applyExistingRecordFilters(state, cleaned) {
    if (!state || !cleaned || typeof cleaned !== "object" || Array.isArray(cleaned)) {
        return;
    }
    for (const [serverKey, stateKey] of Object.entries(FILTER_SERVER_TO_STATE)) {
        if (!(serverKey in cleaned) || state[stateKey] === undefined) {
            continue;
        }
        const value = cleaned[serverKey];
        if (Array.isArray(state[stateKey])) {
            state[stateKey] = Array.isArray(value) ? value : [];
        } else if (typeof state[stateKey] === "string") {
            state[stateKey] = value || "";
        } else {
            state[stateKey] = value || false;
        }
    }
}

/**
 * Write filters, apply any records dropped by the server, and persist.
 */
export async function writeAndSyncFilters(orm, model, wizardId, payload, state, persistFilters) {
    const cleaned = await orm.call(model, "update_filters", [wizardId, payload]);
    applyExistingRecordFilters(state, cleaned);
    persistFilters?.(state);
    return cleaned;
}

/**
 * Ensure a wizard record exists and sync current filter payload to it.
 */
export async function syncReportWizard(orm, {
    model,
    wizardId,
    filterPayload,
    onWizardId,
    onCleanedFilters,
}) {
    let currentId = wizardId;
    if (!currentId) {
        currentId = await orm.call(model, "create", [{}]);
        onWizardId(currentId);
    }
    try {
        const cleaned = await orm.call(model, "update_filters", [currentId, filterPayload]);
        onCleanedFilters?.(cleaned);
        return currentId;
    } catch {
        currentId = await orm.call(model, "create", [{}]);
        onWizardId(currentId);
        const cleaned = await orm.call(model, "update_filters", [currentId, filterPayload]);
        onCleanedFilters?.(cleaned);
        return currentId;
    }
}

export function cloneFilterValue(value) {
    if (Array.isArray(value)) {
        return [...value];
    }
    if (value && typeof value === "object") {
        return { ...value };
    }
    return value;
}

/**
 * Build persisted filter values for initial component state.
 */
export function buildInitialFilterState(savedUi, filterDefaults) {
    const filterState = {};
    for (const [field, defaultValue] of Object.entries(filterDefaults)) {
        const saved = savedUi[field];
        if (
            defaultValue &&
            typeof defaultValue === "object" &&
            !Array.isArray(defaultValue)
        ) {
            const savedObj = saved && typeof saved === "object" && !Array.isArray(saved)
                ? saved
                : {};
            filterState[field] = { ...defaultValue, ...savedObj };
        } else {
            filterState[field] = saved ?? defaultValue;
        }
    }
    return filterState;
}

/**
 * Shared setup for report filter persistence:
 * - breadcrumb back (action localState)
 * - refresh / reopen (per-user localStorage) until the user changes filters
 */
export function setupReportPersistence(props, {
    filterFields = [],
    filterDefaults = {},
    detailCacheField = null,
    reportKey,
} = {}) {
    const storageKey = _storageKey(_reportKey(props, { reportKey }));
    const stored = readStoredFilters(storageKey);
    const savedUi = readSavedReportUiState(props, { filterFields });
    const restoring = Boolean(props.state) || Boolean(stored);

    const filterSource = { ...(stored || {}) };
    for (const field of filterFields) {
        if (Object.prototype.hasOwnProperty.call(savedUi, field)) {
            filterSource[field] = savedUi[field];
        }
    }

    const persistFilters = (state) => {
        if (!state) {
            return;
        }
        const payload = {};
        for (const field of filterFields) {
            payload[field] = cloneFilterValue(state[field]);
        }
        writeStoredFilters(storageKey, payload);
    };

    return {
        savedUi,
        restoring,
        filterDefaults,
        filterState: buildInitialFilterState(filterSource, filterDefaults),
        persistFilters,
        getLocalState: (state) => {
            persistFilters(state);
            return buildReportLocalState(state, {
                filterFields,
                detailCacheField,
            });
        },
    };
}

/**
 * Create or restore wizard and load filters on first open.
 */
export async function bootstrapReportWizard(orm, {
    model,
    restoring,
    getWizardId,
    setWizardId,
    filterPayload,
    loadFiltersFromServer,
    createArgs = [{}],
    state,
    persistFilters,
}) {
    if (restoring) {
        await syncReportWizard(orm, {
            model,
            wizardId: getWizardId(),
            filterPayload,
            onWizardId: setWizardId,
            onCleanedFilters: (cleaned) => {
                applyExistingRecordFilters(state, cleaned);
                persistFilters?.(state);
            },
        });
        return;
    }
    let wizardId = getWizardId();
    if (!wizardId) {
        wizardId = await orm.call(model, "create", createArgs);
        setWizardId(wizardId);
    }
    await loadFiltersFromServer(wizardId);
}
