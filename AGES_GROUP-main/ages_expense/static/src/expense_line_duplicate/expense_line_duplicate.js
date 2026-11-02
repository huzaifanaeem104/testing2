/** @odoo-module **/

import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { x2ManyCommands } from "@web/core/orm_service";

function getContainingList(record) {
    const parent = record._parentRecord;
    if (!parent?.data) {
        return null;
    }
    for (const value of Object.values(parent.data)) {
        if (value && Array.isArray(value.records) && value.records.includes(record)) {
            return value;
        }
    }
    return null;
}

function many2oneTuple(value) {
    if (!value) {
        return false;
    }
    if (Array.isArray(value)) {
        return value[0] ? [value[0], value[1] || ""] : false;
    }
    if (typeof value === "number") {
        return [value, undefined];
    }
    const id = value.id || value.resId;
    if (!id) {
        return false;
    }
    return [id, value.display_name || value.displayName || undefined];
}

function many2oneId(value) {
    const tuple = many2oneTuple(value);
    return tuple ? tuple[0] : false;
}

function snapshotLineValues(record) {
    const data = record.data || {};
    const attachmentIds = (data.attachment_ids?.records || [])
        .map((rec) => rec.resId)
        .filter(Boolean);
    return {
        account_id: many2oneTuple(data.account_id),
        partner_id: many2oneTuple(data.partner_id),
        project_id: many2oneTuple(data.project_id),
        name: data.name || "",
        amount: data.amount || 0,
        sequence: (data.sequence || 10) + 1,
        attachmentIds,
    };
}

function moveRecordAfter(list, source, moved) {
    const srcIdx = list.records.indexOf(source);
    const movedIdx = list.records.indexOf(moved);
    if (srcIdx < 0 || movedIdx < 0 || movedIdx === srcIdx + 1) {
        return;
    }
    list.records.splice(movedIdx, 1);
    list.records.splice(list.records.indexOf(source) + 1, 0, moved);

    const srcId = source.resId || source._virtualId;
    const movedId = moved.resId || moved._virtualId;
    const ids = list._currentIds;
    if (!ids) {
        return;
    }
    const idMoved = ids.indexOf(movedId);
    if (idMoved >= 0) {
        ids.splice(idMoved, 1);
    }
    const idSrc = ids.indexOf(srcId);
    ids.splice(idSrc + 1, 0, movedId);
}

export class ExpenseLineDuplicate extends Component {
    static props = { ...standardWidgetProps };
    static template = xml`
        <button type="button"
                class="btn btn-link p-0 ages_expense_dup_btn"
                title="Duplicate"
                t-att-disabled="isDisabled"
                t-on-click.stop.prevent="onDuplicate">
            <i class="fa fa-copy"/>
        </button>
    `;

    get isDisabled() {
        const parentState =
            this.props.record.evalContext?.parent?.state ||
            this.props.record._parentRecord?.data?.state;
        return parentState === "approved" || parentState === "cancelled";
    }

    async onDuplicate() {
        if (this.isDisabled) {
            return;
        }
        const record = this.props.record;
        const list = getContainingList(record);
        if (!list?.addNewRecord) {
            return;
        }
        const snap = snapshotLineValues(record);
        const newRecord = await list.addNewRecord({
            position: "bottom",
            context: {
                default_account_id: many2oneId(snap.account_id),
                default_partner_id: many2oneId(snap.partner_id),
                default_project_id: many2oneId(snap.project_id),
                default_name: snap.name,
                default_amount: snap.amount,
                default_sequence: snap.sequence,
            },
            mode: "edit",
        });
        const values = {
            account_id: snap.account_id,
            partner_id: snap.partner_id,
            project_id: snap.project_id,
            name: snap.name,
            amount: snap.amount,
            sequence: snap.sequence,
        };
        if (snap.attachmentIds.length && newRecord.fields.attachment_ids) {
            values.attachment_ids = [x2ManyCommands.set(snap.attachmentIds)];
        }
        await newRecord.update(values);
        moveRecordAfter(list, record, newRecord);
        if (list.enterEditMode) {
            await list.enterEditMode(newRecord);
        }
    }
}

export const expenseLineDuplicate = {
    component: ExpenseLineDuplicate,
    listViewWidth: 36,
};

registry.category("view_widgets").add("ages_expense_duplicate_line", expenseLineDuplicate);
