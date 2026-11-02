/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class StockBarcodeClient extends Component {
    static template = "stock_barcode.Client";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.barcode = useService("barcode");
        const ctx = this.props.action.context || {};
        this.state = useState({
            mode: ctx.inventory ? "inventory" : ctx.picking_id ? "picking" : "home",
            pickingId: ctx.picking_id || false,
            pickingTypeId: ctx.picking_type_id || false,
            locationId: false,
            data: {},
            message: "",
        });
        onWillStart(() => this.reload());
        this.barcode.bus.addEventListener("barcode_scanned", (ev) => {
            this.onBarcodeScanned(ev.detail.barcode);
        });
    }

    get lines() {
        return this.state.data.lines || [];
    }

    get pickings() {
        return this.state.data.pickings || [];
    }

    async reload() {
        if (this.state.mode === "inventory") {
            this.state.data = await this.orm.call("stock.quant", "get_inventory_barcode_data", [
                this.state.locationId,
            ]);
            return;
        }
        this.state.data = await this.orm.call("stock.picking", "get_barcode_data", [
            this.state.pickingId,
            this.state.pickingTypeId,
        ]);
    }

    async onBarcodeScanned(barcode) {
        try {
            if (this.state.mode === "inventory") {
                this.state.data = await this.orm.call("stock.quant", "process_inventory_barcode", [
                    barcode,
                    this.state.locationId,
                ]);
                this.state.locationId = this.state.data.location && this.state.data.location[0]
                    ? this.state.data.location[0].id
                    : this.state.locationId;
                this.state.message = `Scanned ${barcode}`;
                return;
            }
            if (!this.state.pickingId) {
                this.state.message = "Open a transfer first, then scan products.";
                return;
            }
            this.state.data.lines = await this.orm.call("stock.picking", "process_barcode", [
                [this.state.pickingId],
                barcode,
            ]);
            this.state.message = `Scanned ${barcode}`;
        } catch (error) {
            this.notification.add(error.data?.message || error.message, { type: "danger" });
        }
    }

    async openPicking(pickingId) {
        this.state.pickingId = pickingId;
        this.state.mode = "picking";
        await this.reload();
    }

    async openInventory() {
        this.state.mode = "inventory";
        this.state.pickingId = false;
        await this.reload();
    }

    async validate() {
        try {
            if (this.state.mode === "inventory") {
                await this.orm.call("stock.quant", "action_barcode_apply_inventory", [
                    this.state.locationId,
                ]);
                this.notification.add("Inventory count applied.", { type: "success" });
                await this.reload();
                return;
            }
            const action = await this.orm.call("stock.picking", "action_barcode_validate", [
                [this.state.pickingId],
            ]);
            if (action && action.type) {
                await this.action.doAction(action);
            } else {
                this.notification.add("Transfer validated.", { type: "success" });
            }
            this.state.pickingId = false;
            this.state.mode = "home";
            await this.reload();
        } catch (error) {
            this.notification.add(error.data?.message || error.message, { type: "danger" });
        }
    }
}

registry.category("actions").add("stock_barcode_client", StockBarcodeClient);
