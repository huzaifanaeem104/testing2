/** @odoo-module **/

import { Component, onMounted, onWillUnmount, onWillUpdateProps, useRef } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";

function cssVar(name, fallback) {
    const root = document.querySelector(".o_ages_ent_dashboard") || document.documentElement;
    const value = getComputedStyle(root).getPropertyValue(name).trim();
    return value || fallback;
}

function palette() {
    return [
        cssVar("--ages-ent-accent", "#8b1a1a"),
        cssVar("--ages-ent-expense", cssVar("--ages-ent-danger", "#c0455a")),
        cssVar("--ages-ent-success", cssVar("--msu-success", "#0f766e")),
        cssVar("--ages-ent-warning", cssVar("--msu-warning", "#b45309")),
        cssVar("--ages-ent-info", cssVar("--msu-info", "#017e84")),
        "#c2410c",
        cssVar("--ages-ent-muted", cssVar("--msu-text-muted", "#5c6b7f")),
        "#334155",
    ];
}

function seriesColor(label, index, colors) {
    const key = String(label || "").toLowerCase();
    if (/(revenue|inflow|income|ordered)/.test(key)) {
        return colors[0];
    }
    if (/(expense|outflow|cost|deduction)/.test(key)) {
        return colors[1];
    }
    if (/(result|net|profit|margin)/.test(key)) {
        return colors[2];
    }
    return colors[index % colors.length];
}

function chartHasValues(spec) {
    const labels = spec?.labels || [];
    const datasets = spec?.datasets || [];
    return Boolean(labels.length && datasets.some((dataset) => (dataset.data || []).some((value) => Number(value))));
}

function compactNumber(value, unit) {
    const num = Number(value) || 0;
    if (unit === "percent") {
        return `${Math.round(num)}%`;
    }
    if (unit === "hours") {
        return `${Math.round(num).toLocaleString()} h`;
    }
    const abs = Math.abs(num);
    let scaled = num;
    let suffix = "";
    if (abs >= 1e6) {
        scaled = num / 1e6;
        suffix = "M";
    } else if (abs >= 1e3) {
        scaled = num / 1e3;
        suffix = "k";
    }
    const digits = suffix ? 1 : (abs >= 100 ? 0 : 1);
    const body = `${scaled.toFixed(digits)}${suffix}`.replace(/\.0([kM])?$/, "$1");
    return body;
}

function formatTooltipValue(value, unit, currency) {
    const num = Number(value) || 0;
    if (unit === "percent") {
        return `${num.toFixed(1)}%`;
    }
    if (unit === "hours") {
        return `${num.toLocaleString(undefined, { maximumFractionDigits: 1 })} h`;
    }
    if (unit === "money") {
        const code = currency?.name || currency?.symbol || "";
        return `${code} ${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}`.trim();
    }
    return num.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const CHARTJS_TYPES = new Set(["bar", "line", "doughnut", "pie", "radar", "polarArea", "scatter", "bubble"]);

function chartJsType(type) {
    if (type === "area" || type === "sparkline") {
        return "line";
    }
    if (type === "horizontalBar" || type === "stackedBar" || type === "waterfall" || type === "mixed") {
        return "bar";
    }
    if (type === "gauge" || type === "pie") {
        return "doughnut";
    }
    return CHARTJS_TYPES.has(type) ? type : "bar";
}

function cloneData(data) {
    return Array.isArray(data) ? data.map((value) => Number(value) || 0) : [];
}

function specSignature(spec) {
    if (!spec) {
        return "";
    }
    const datasets = spec.datasets || [];
    const dataPart = datasets.map((dataset) => {
        const values = Array.isArray(dataset.data) ? dataset.data.join(",") : "";
        return `${dataset.label || ""}:${dataset.hidden ? 1 : 0}:${dataset.type || ""}:${values}`;
    }).join("|");
    return [
        spec.title || "",
        (spec.labels || []).join(","),
        spec.type || "",
        spec.series_sig || "",
        spec.highlight_latest ? 1 : 0,
        dataPart,
    ].join("::");
}

export class AgesEntChart extends Component {
    static template = "ages_enterprise_dashboard.Chart";
    static props = {
        spec: { type: Object, optional: true },
        onSelect: { type: Function, optional: true },
        currency: { type: Object, optional: true },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = null;
        this._renderToken = 0;
        this._lastSig = "";
        this._rendering = false;
        onMounted(() => {
            this._lastSig = specSignature(this.props.spec);
            this.renderChart(this.props.spec);
        });
        onWillUpdateProps((nextProps) => {
            const nextSig = specSignature(nextProps.spec);
            if (nextSig === this._lastSig) {
                return;
            }
            this._lastSig = nextSig;
            this.renderChart(nextProps.spec);
        });
        onWillUnmount(() => {
            this._renderToken += 1;
            this.destroyChart();
        });
    }

    get ariaLabel() {
        const spec = this.props.spec || {};
        return [spec.title, spec.unit].filter(Boolean).join(" · ");
    }

    get centerLabel() {
        return (this.props.spec || {}).center_label || "";
    }

    get sizeClass() {
        const size = (this.props.spec || {}).size || ((this.props.spec || {}).variant === "sparkline" ? "spark" : "md");
        return `is-${size}`;
    }

    destroyChart() {
        try {
            if (this.chart) {
                this.chart.destroy();
                this.chart = null;
            }
            const canvas = this.canvasRef.el;
            const Chart = window.Chart;
            if (canvas && Chart?.getChart) {
                const existing = Chart.getChart(canvas);
                if (existing) {
                    existing.destroy();
                }
            }
        } catch (_error) {
            this.chart = null;
        }
    }

    async renderChart(spec) {
        spec = spec || this.props.spec;
        const token = ++this._renderToken;
        if (!spec || !this.canvasRef.el) {
            return;
        }
        if (spec.empty || !chartHasValues(spec)) {
            this.destroyChart();
            return;
        }
        if (this._rendering) {
            // A newer token already queued; finish after current turn.
        }
        this._rendering = true;
        try {
            await loadBundle("web.chartjs_lib");
            if (token !== this._renderToken || !this.canvasRef.el) {
                return;
            }
            const Chart = window.Chart;
            if (!Chart) {
                return;
            }
            this.destroyChart();
            if (token !== this._renderToken || !this.canvasRef.el) {
                return;
            }

            const colors = palette();
            const ink = cssVar("--ages-ent-ink", cssVar("--msu-text", "#334155"));
            const muted = cssVar("--ages-ent-muted", cssVar("--msu-text-muted", "#64748b"));
            const line = cssVar("--ages-ent-line", "#e7e7ee");
            const success = cssVar("--ages-ent-success", "#0f766e");
            const danger = cssVar("--ages-ent-danger", "#b42318");
            const labels = [...(spec.labels || [])];
            const variant = spec.variant || spec.type;
            const forcedType = spec.force_dataset_type || false;
            const isArea = spec.type === "area" || spec.type === "sparkline" || variant === "sparkline" || forcedType === "area";
            const isHorizontal = !forcedType && spec.type === "horizontalBar";
            const isDoughnut = ["doughnut", "pie", "gauge"].includes(spec.type);
            const isSpark = variant === "sparkline" || spec.type === "sparkline";
            const isGauge = spec.type === "gauge" || variant === "gauge";
            const isWaterfall = !forcedType && variant === "waterfall";
            const stacked = !forcedType && (Boolean(spec.stacked) || spec.type === "stackedBar" || isWaterfall);
            const unit = spec.unit || "count";
            const currency = this.props.currency || {};
            const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

            const datasets = (spec.datasets || []).map((dataset, index) => {
                const color = seriesColor(dataset.label, index, colors);
                const sourceType = forcedType
                    ? (forcedType === "area" ? "line" : forcedType)
                    : (dataset.type || (isArea ? "line" : (isHorizontal || isWaterfall || spec.type === "stackedBar" ? "bar" : spec.type)));
                const mappedType = chartJsType(sourceType);
                const hidden = Boolean(dataset.hidden) || (isWaterfall && index === 0);
                const data = cloneData(dataset.data);
                const doughnutColors = isDoughnut
                    ? data.map((_, sliceIndex) => colors[sliceIndex % colors.length])
                    : null;
                let backgroundColor = hidden
                    ? "transparent"
                    : (isWaterfall && index === 1
                        ? success
                        : (isWaterfall && index === 2
                            ? danger
                            : (doughnutColors || color)));
                if (spec.highlight_latest && !isDoughnut && !isSpark && data.length && !doughnutColors) {
                    const last = data.length - 1;
                    backgroundColor = data.map((_, pointIndex) => (
                        pointIndex === last ? color : "rgba(92, 107, 127, 0.22)"
                    ));
                }
                return {
                    type: mappedType,
                    label: dataset.label,
                    data,
                    backgroundColor,
                    borderColor: hidden
                        ? "transparent"
                        : (isDoughnut ? cssVar("--ages-ent-card", "#ffffff") : color),
                    fill: isArea || dataset.fill === true,
                    tension: isSpark ? 0.35 : 0.25,
                    borderDash: dataset.borderDash || (String(dataset.label || "").includes("(prev)") ? [4, 4] : undefined),
                    order: dataset.order,
                    yAxisID: dataset.yAxisID,
                    hidden,
                    pointRadius: isSpark ? 0 : (mappedType === "line" ? 2 : 0),
                    borderWidth: isSpark ? 1.5 : (isDoughnut ? 2 : 1.5),
                };
            });

            if (isGauge && datasets[0]) {
                datasets[0].backgroundColor = [
                    cssVar("--ages-ent-success", "#0f766e"),
                    cssVar("--ages-ent-line", "#e7e7ee"),
                ];
                datasets[0].borderWidth = 0;
            }

            const hideLegend = isSpark || isGauge || datasets.filter((item) => !item.hidden).length <= 1;
            this.chart = new Chart(this.canvasRef.el, {
                type: chartJsType(forcedType || spec.type),
                data: { labels, datasets },
                options: {
                    ...(isHorizontal ? { indexAxis: "y" } : {}),
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: {
                        mode: isDoughnut ? "nearest" : "index",
                        intersect: false,
                    },
                    onClick: (_event, elements) => {
                        if (!elements.length || !this.props.onSelect || isSpark) {
                            return;
                        }
                        const index = elements[0].index;
                        this.props.onSelect({
                            index,
                            label: labels[index],
                            actionKey: spec.action_key,
                            groupField: spec.group_field,
                            resId: (spec.label_ids || [])[index],
                        });
                    },
                    plugins: {
                        legend: {
                            display: !hideLegend || (isDoughnut && labels.length > 1),
                            position: isDoughnut ? "bottom" : "top",
                            labels: {
                                color: ink,
                                usePointStyle: true,
                                boxWidth: 8,
                                padding: isDoughnut ? 14 : 10,
                                font: { size: 11 },
                                filter: (item) => item.text !== "Base",
                            },
                        },
                        title: { display: false },
                        tooltip: {
                            callbacks: {
                                title: (items) => (items[0] && items[0].label) || "",
                                label: (item) => `${item.dataset.label}: ${formatTooltipValue(item.raw, unit, currency)}`,
                                footer: () => (spec.action_key && !isSpark ? "Click to open records" : ""),
                            },
                        },
                    },
                    scales: isDoughnut || isSpark ? (
                        isSpark ? {
                            x: { display: false },
                            y: { display: false },
                        } : {}
                    ) : {
                        x: {
                            stacked,
                            border: { display: false },
                            grid: { color: line, drawBorder: false, display: !isHorizontal },
                            ticks: {
                                color: muted,
                                maxRotation: 0,
                                autoSkip: true,
                                callback: (value) => {
                                    const label = isHorizontal ? compactNumber(value, unit) : labels[value] || value;
                                    const text = String(label);
                                    return text.length > 16 ? `${text.slice(0, 14)}…` : text;
                                },
                            },
                        },
                        y: {
                            stacked,
                            beginAtZero: spec.y_begin_at_zero !== false,
                            border: { display: false },
                            grid: { color: line, drawBorder: false },
                            ticks: {
                                color: muted,
                                callback: (value) => compactNumber(value, unit),
                            },
                        },
                    },
                    cutout: isDoughnut ? (isGauge ? "72%" : "74%") : undefined,
                    layout: isDoughnut ? { padding: { top: 4, bottom: 2 } } : undefined,
                },
            });
        } catch (_error) {
            // Keep UI alive if Chart.js rejects a type switch / canvas reuse.
            this.destroyChart();
        } finally {
            if (token === this._renderToken) {
                this._rendering = false;
            }
        }
    }
}
