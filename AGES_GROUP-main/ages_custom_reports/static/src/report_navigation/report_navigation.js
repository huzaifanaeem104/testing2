/** @odoo-module **/

const HIGHLIGHT_STORAGE_KEY = "ages_highlight_move_line_id";
const TAB_DONE_KEY = "ages_highlight_aml_tab_done";

export function rememberHighlightMoveLine(moveLineId) {
    try {
        if (moveLineId) {
            sessionStorage.setItem(HIGHLIGHT_STORAGE_KEY, String(moveLineId));
            sessionStorage.removeItem(TAB_DONE_KEY);
        } else {
            sessionStorage.removeItem(HIGHLIGHT_STORAGE_KEY);
            sessionStorage.removeItem(TAB_DONE_KEY);
        }
    } catch (_err) {
        // Ignore private-mode / disabled storage.
    }
}

function _highlightContext(moveLineId) {
    rememberHighlightMoveLine(moveLineId);
    if (!moveLineId) {
        return {};
    }
    return { ages_highlight_move_line_id: moveLineId };
}

function _postedDomain(targetMove) {
    if (targetMove === "posted") {
        return [["parent_state", "=", "posted"]];
    }
    if (targetMove === "draft") {
        return [["parent_state", "=", "draft"]];
    }
    return [];
}

function _dateDomain(dateFrom, dateTo) {
    const domain = [];
    if (dateFrom) {
        domain.push(["date", ">=", dateFrom]);
    }
    if (dateTo) {
        domain.push(["date", "<=", dateTo]);
    }
    return domain;
}

export function buildJournalEntryAction(moveId, name, options = {}) {
    const action = {
        type: "ir.actions.act_window",
        name: name || "Journal Entry",
        res_model: "account.move",
        res_id: moveId,
        views: [[false, "form"]],
        target: "current",
    };
    const moveLineId = options.moveLineId || options.highlightMoveLineId;
    action.context = {
        ...(action.context || {}),
        ..._highlightContext(moveLineId),
    };
    return action;
}

export function buildPartnerAction(partnerId, name) {
    return {
        type: "ir.actions.act_window",
        name: name || "Partner",
        res_model: "res.partner",
        res_id: partnerId,
        views: [[false, "form"]],
        target: "current",
    };
}

export function buildJournalItemsForAccountAction({
    accountId,
    accountName,
    dateFrom,
    dateTo,
    targetMove,
    highlightMoveLineId,
}) {
    return {
        type: "ir.actions.act_window",
        name: accountName || "Journal Items",
        res_model: "account.move.line",
        view_mode: "list",
        views: [[false, "list"]],
        domain: [
            ["account_id", "=", accountId],
            ..._dateDomain(dateFrom, dateTo),
            ..._postedDomain(targetMove),
        ],
        context: _highlightContext(highlightMoveLineId),
        target: "current",
    };
}

export function buildJournalItemsForPartnerAction({
    partnerId,
    partnerName,
    dateFrom,
    dateTo,
    targetMove,
    analyticAccountId,
}) {
    const domain = [
        ["partner_id", "=", partnerId || false],
        ..._dateDomain(dateFrom, dateTo),
        ..._postedDomain(targetMove),
    ];
    if (analyticAccountId) {
        domain.push(["analytic_distribution", "ilike", `"${analyticAccountId}"`]);
    }
    return {
        type: "ir.actions.act_window",
        name: partnerName || "Journal Items",
        res_model: "account.move.line",
        view_mode: "list",
        views: [[false, "list"]],
        domain,
        target: "current",
    };
}

export function buildMoveLineListAction({ name, domain, highlightMoveLineId }) {
    const action = {
        type: "ir.actions.act_window",
        name: name || "Journal Items",
        res_model: "account.move.line",
        view_mode: "list",
        views: [[false, "list"]],
        domain,
        target: "current",
    };
    action.context = {
        ...(action.context || {}),
        ..._highlightContext(highlightMoveLineId),
    };
    return action;
}

export function buildGeneralLedgerClientAction({
    accountId,
    dateFrom,
    dateTo,
    targetMove,
    journalIds,
    analyticAccountId,
    parentName,
}) {
    const initialFilters = {
        date_from: dateFrom || false,
        date_to: dateTo || false,
        target_move: targetMove || "posted",
        unfold_all: true,
    };
    if (journalIds?.length) {
        initialFilters.journal_ids = [[6, 0, journalIds]];
    }
    if (analyticAccountId) {
        initialFilters.analytic_account_id = analyticAccountId;
    }
    if (accountId) {
        initialFilters.account_ids = [[6, 0, [accountId]]];
    }
    return {
        type: "ir.actions.client",
        tag: "ages_general_ledger_report",
        name: parentName ? `${parentName} / General Ledger` : "General Ledger",
        params: {
            account_id: accountId,
            initial_filters: initialFilters,
        },
    };
}

export function buildJournalAuditMoveLinesAction({
    name,
    journalId,
    accountId,
    dateFrom,
    dateTo,
    targetMove,
}) {
    const domain = [];
    if (journalId) {
        domain.push(["journal_id", "=", journalId]);
    }
    if (accountId) {
        domain.push(["account_id", "=", accountId]);
    }
    domain.push(..._dateDomain(dateFrom, dateTo));
    domain.push(..._postedDomain(targetMove));
    return buildMoveLineListAction({ name, domain });
}

export function buildTaxAuditAction({ taxId, dateFrom, dateTo, targetMove }) {
    return buildMoveLineListAction({
        name: "Tax Audit",
        domain: [
            ["tax_line_id", "=", taxId],
            ..._dateDomain(dateFrom, dateTo),
            ..._postedDomain(targetMove),
        ],
    });
}

export function buildTaxGridAuditAction({ tagIds, dateFrom, dateTo, targetMove }) {
    return buildMoveLineListAction({
        name: "Tax Grid Audit",
        domain: [
            ["tax_tag_ids", "in", tagIds || []],
            ..._dateDomain(dateFrom, dateTo),
            ..._postedDomain(targetMove),
        ],
    });
}
