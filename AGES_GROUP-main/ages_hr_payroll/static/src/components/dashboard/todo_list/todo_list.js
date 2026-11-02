/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, onWillStart, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { orderByToString } from "@web/search/utils/order_by";
import { Field } from "@web/views/fields/field";
import { Record } from "@web/model/record";
import { useSetupAction } from "@web/search/action_hook";

export class PayrollDashboardTodo extends Component {
    static template = "ages_hr_payroll.TodoList";
    static components = { Field, Record };
    static props = ["orderBy"];

    setup() {
        this.company = useService("company");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = useState({
            activeNoteId: -1,
            isEditingNoteName: false,
            records: [],
        });
        this.recordInfo = {
            model: "hr.payroll.note",
            specification: { name: {} },
        };
        this.autofocusInput = useAutofocus({ selectAll: true });
        useSetupAction({
            beforeLeave: () => this.saveNote(),
            beforeUnload: () => {
                if (this.editedNote) {
                    return this.editedNote.urgentSave();
                }
            },
        });

        onWillStart(async () => {
            this.state.records = (
                await this.orm.webSearchRead(this.recordInfo.model, [], {
                    specification: this.recordInfo.specification,
                    order: orderByToString(this.props.orderBy),
                })
            ).records;
            const record = this.state.records[0];
            this.state.activeNoteId = record && record.id;
        });
    }

    async createNoteForm() {
        const result = await this.orm.create("hr.payroll.note", [{
            name: "Untitled",
            company_id: this.company.currentCompany.id,
            note: "",
        }]);
        const noteId = result[0];
        const createdNote = (
            await this.orm.webRead(this.recordInfo.model, [noteId], {
                specification: this.recordInfo.specification,
            })
        )[0];
        this.state.records.push(createdNote);
        this.state.activeNoteId = noteId;
        this.startNameEdition(createdNote);
    }

    async onClickNoteTab(record) {
        if (record.id === this.state.activeNoteId) {
            return;
        }
        await this.saveNote();
        this.state.isEditingNoteName = false;
        this.state.activeNoteId = record.id;
    }

    onRecordChanged(editedRecord) {
        this.editedNote = editedRecord;
    }

    startNameEdition(record) {
        if (record.id === this.state.activeNoteId) {
            this.state.isEditingNoteName = true;
            this.bufferedText = record.name;
        }
    }

    onInputNoteNameInput(ev) {
        this.bufferedText = ev.target.value;
    }

    handleBlur() {
        this._applyNoteRename();
    }

    onKeyDownNoteNameInput(ev) {
        if (ev.key === "Enter") {
            this._applyNoteRename();
        } else if (ev.key === "Escape") {
            this.state.isEditingNoteName = false;
        }
    }

    async _applyNoteRename() {
        const value = this.bufferedText.trim();
        const record = this.state.records.find((rec) => rec.id === this.state.activeNoteId);
        if (value !== record.name) {
            record.name = value;
            this.orm.write(this.recordInfo.model, [record.id], { name: value });
        }
        this.state.isEditingNoteName = false;
    }

    async onNoteDelete() {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Are you sure you want to delete this note? All content will be definitely lost."),
            confirm: () => this._deleteNote(this.state.activeNoteId),
        });
    }

    async _deleteNote(noteId) {
        await this.orm.unlink(this.recordInfo.model, [noteId]);
        this.state.records = this.state.records.filter((record) => record.id !== noteId);
        this.state.activeNoteId = this.state.records.length && this.state.records[0].id;
    }

    async onClickCreateNote() {
        await this.saveNote();
        this.createNoteForm();
    }

    async saveNote() {
        if (this.editedNote) {
            this.editedNote.save();
        }
    }
}
