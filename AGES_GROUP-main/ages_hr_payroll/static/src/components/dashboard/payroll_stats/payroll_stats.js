/** @odoo-module **/

import { loadJS } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
import { getColor, getCustomColor } from "@web/core/colors/colors";
import { cookie } from "@web/core/browser/cookie";
import { Component, onWillUnmount, useEffect, useRef, useState, onWillStart } from "@odoo/owl";

const colorScheme = cookie.get("color_scheme");
const GRAPH_GRID_COLOR = getCustomColor(colorScheme, "#d8dadd", "#3C3E4B");
const GRAPH_LABEL_COLOR = getCustomColor(colorScheme, "#111827", "#E4E4E4");

export class PayrollDashboardStats extends Component {
    static template = "ages_hr_payroll.DashboardStats";
    static props = {
        title: String,
        help: { type: String, optional: true },
        id: { type: String, optional: true },
        actions: Array,
        type: String,
        data: Object,
        is_sample: Boolean,
        label: String,
    };

    setup() {
        this.actionService = useService("action");
        this.canvasRef = useRef("canvas");
        this.state = useState({ monthly: true });
        onWillStart(() => loadJS("/web/static/lib/Chart/Chart.js"));
        useEffect(() => this.renderChart());
        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }

    toggle() {
        this.state.monthly = !this.state.monthly;
    }

    get graphData() {
        return this.props.data[this.state.monthly ? "monthly" : "yearly"];
    }

    renderChart() {
        if (!this.canvasRef.el) {
            return;
        }
        if (this.chart) {
            this.chart.destroy();
        }
        const ctx = this.canvasRef.el.getContext("2d");
        this.chart = new Chart(ctx, this.getChartConfig());
    }

    getChartConfig() {
        if (this.props.type === "bar") {
            return this.getBarChartConfig();
        }
        if (this.props.type === "stacked_bar") {
            return this.getStackedBarChartConfig();
        }
        return {};
    }

    getBarChartConfig() {
        const data = [];
        const labels = [];
        const backgroundColors = [];
        const color19 = getColor(1, cookie.get("color_scheme"), "odoo");
        this.graphData.forEach((pt) => {
            data.push(pt.value);
            labels.push(pt.label);
            let color;
            if (this.props.is_sample) {
                color = "#ebebeb";
            } else if (pt.type === "past") {
                color = "#ccbdc8";
            } else if (pt.type === "future") {
                color = "#a5d8d7";
            } else {
                color = color19;
            }
            backgroundColors.push(color);
        });
        return {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    data,
                    label: this.props.label,
                    backgroundColor: backgroundColors,
                }],
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: { intersect: false, position: "nearest", caretSize: 0 },
                },
                scales: {
                    y: {
                        grid: { color: GRAPH_GRID_COLOR },
                        ticks: { color: GRAPH_LABEL_COLOR },
                    },
                    x: {
                        grid: { color: GRAPH_GRID_COLOR },
                        ticks: { color: GRAPH_LABEL_COLOR },
                    },
                },
                maintainAspectRatio: false,
            },
        };
    }

    getStackedBarChartConfig() {
        const labels = [];
        const datasets = [];
        const datasetLabels = [];
        const colors = this.props.is_sample
            ? ["#e7e7e7", "#dddddd", "#f0f0f0", "#fafafa"]
            : [getColor(14, cookie.get("color_scheme"), "odoo"), "#a5d8d7", "#ebebeb", "#ebebeb"];

        Object.entries(this.graphData).forEach(([code, graphData]) => {
            datasetLabels.push(code);
            const datasetData = [];
            const formattedData = [];
            graphData.forEach((pt) => {
                if (!labels.includes(pt.label)) {
                    labels.push(pt.label);
                }
                formattedData.push(`${code}: ${pt.formatted_value || pt.value}`);
                datasetData.push(pt.value);
            });
            datasets.push({
                data: datasetData,
                label: code,
                backgroundColor: colors[datasetLabels.length - 1],
                formatted_data: formattedData,
            });
        });

        return {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        intersect: false,
                        position: "nearest",
                        caretSize: 0,
                        callbacks: {
                            label: (tooltipItem) => {
                                const { datasetIndex, index } = tooltipItem;
                                return datasets[datasetIndex].formatted_data[index];
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        stacked: true,
                        grid: { color: GRAPH_GRID_COLOR },
                        ticks: { color: GRAPH_LABEL_COLOR },
                    },
                    y: {
                        display: false,
                        stacked: true,
                        beginAtZero: true,
                    },
                },
                maintainAspectRatio: false,
            },
        };
    }
}
