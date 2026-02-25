/**
 * 通用期权交易监控 - 多标的仪表盘视图
 *
 * 不依赖任何具体策略逻辑（如 MACD、TD 等），
 * 根据后端返回的 indicators 字段动态渲染图表。
 */

let charts = {};
let autoRefreshTimer = null;
let currentVariant = null;
let selectedMonth = "all";
let lastData = null;

const INDICATOR_COLORS = [
    '#ff9f0a', '#0a84ff', '#30d158', '#ff453a', '#bf5af2',
    '#64d2ff', '#ffd60a', '#ff6482', '#ac8e68', '#5e5ce6'
];

function initMonitor(variant) {
    currentVariant = variant;
    loadStrategyList();

    $("#auto-refresh-switch").on("change", function () {
        if (this.checked) startAutoRefresh();
        else stopAutoRefresh();
    });

    $("#strategy-selector").on("change", function () {
        var v = $(this).val();
        if (v && v !== currentVariant) window.location.href = "/dashboard/" + v;
    });

    $("#month-filter-container").on("change", ".btn-check", function () {
        selectedMonth = $(this).val();
        if (lastData) updateDashboard(lastData);
    });

    fetchData();
    startAutoRefresh();
}

function fetchData() {
    if (!currentVariant) return;
    $.getJSON("/api/data/" + currentVariant + "?t=" + Date.now(), function (data) {
        lastData = data;
        updateDashboard(data);
    }).fail(function () {
        console.log("fetch failed");
    });
}

function updateDashboard(data) {
    $("#last-update").text(data.timestamp);
    updateTables(data.positions, data.orders);
    updateMonthButtons(data.instruments);

    var container = $("#charts-area");
    if (container.find(".spinner-border").length > 0) container.empty();

    var symbols = Object.keys(data.instruments);
    if (symbols.length === 0) {
        if (container.children().length === 0)
            container.html('<div class="alert alert-info">No data.</div>');
        return;
    }

    symbols.forEach(function (symbol) {
        var inst = data.instruments[symbol];
        var chartId = "chart-" + symbol.replace(/[\.\/]/g, "-");
        var wrapperId = "wrapper-" + chartId;
        var isVisible = (selectedMonth === "all" || inst.delivery_month === selectedMonth);

        if ($("#" + chartId).length === 0) {
            container.append(
                '<div id="' + wrapperId + '" class="mb-4 instrument-wrapper">' +
                '<div class="instrument-header"><h5 class="mb-0">' + symbol +
                ' <small class="text-muted" style="font-size:0.6em;">(' + (inst.delivery_month || '') + ')</small></h5></div>' +
                '<div id="' + chartId + '" class="chart-container" style="height:600px;"></div></div>'
            );
            charts[symbol] = echarts.init(document.getElementById(chartId));
            window.addEventListener("resize", function () { charts[symbol].resize(); });
        }

        var wrapper = $("#" + wrapperId);
        if (isVisible) {
            wrapper.show();
            renderChart(charts[symbol], symbol, inst);
        } else {
            wrapper.hide();
        }
    });
}

function updateMonthButtons(instruments) {
    var months = new Set();
    Object.values(instruments).forEach(function (inst) {
        if (inst.delivery_month) months.add(inst.delivery_month);
    });
    var sorted = Array.from(months).sort();
    var container = $("#month-filter-container");
    var existing = container.find(".btn-check").length - 1;
    if (existing === sorted.length) return;

    var allBtn = container.find("#month-all");
    var allLabel = container.find("label[for='month-all']");
    container.empty().append(allBtn).append(allLabel);

    sorted.forEach(function (m) {
        var id = "month-" + m;
        var checked = (selectedMonth === m) ? "checked" : "";
        container.append(
            '<input type="radio" class="btn-check" name="month-radio" id="' + id + '" value="' + m + '" ' + checked + '>' +
            '<label class="btn btn-outline-primary" for="' + id + '">' + m + '</label>'
        );
    });
}

function updateTables(positions, orders) {
    var posBody = $("#positions-table tbody");
    posBody.empty();
    if (!positions || positions.length === 0) {
        posBody.append('<tr><td colspan="4" class="text-center text-muted">No positions</td></tr>');
    } else {
        positions.forEach(function (p) {
            posBody.append('<tr><td>' + p.vt_symbol + '</td><td>' + p.direction + '</td><td>' + p.volume + '</td><td>' + (p.pnl || 0).toFixed(2) + '</td></tr>');
        });
    }

    var ordBody = $("#orders-table tbody");
    ordBody.empty();
    if (!orders || orders.length === 0) {
        ordBody.append('<tr><td colspan="4" class="text-center text-muted">No orders</td></tr>');
    } else {
        orders.forEach(function (o) {
            ordBody.append('<tr><td title="' + o.vt_orderid + '">' + (o.vt_orderid || '').split('.')[0] + '</td><td>' + o.direction + '</td><td>' + o.price + '</td><td>' + o.status + '</td></tr>');
        });
    }
}

/**
 * 通用图表渲染 - 根据 indicators 动态构建副图和叠加指标
 *
 * indicators 约定格式:
 * {
 *   "sub_charts": [{ "name": "...", "series": [{ "name": "...", "type": "bar|line", "data": [...] }] }],
 *   "overlays": [{ "name": "MA5", "type": "line", "data": [...] }],
 *   "marks": [{ "coord": [idx, price], "value": "9", "position": "top", "type": "buy" }]
 * }
 */
function renderChart(chart, symbol, data) {
    var dates = data.dates || [];
    var ohlc = data.ohlc || [];
    var indicators = data.indicators || {};

    var subCharts = indicators.sub_charts || [];
    var overlays = indicators.overlays || [];
    var marks = indicators.marks || [];

    var subCount = subCharts.length;
    var mainH = subCount > 0 ? 55 : 75;
    var subH = subCount > 0 ? Math.floor(30 / subCount) : 0;

    var grids = [{ left: "5%", right: "5%", top: "5%", height: mainH + "%" }];
    var xAxes = [{
        type: "category", data: dates, scale: true, boundaryGap: false,
        axisLine: { onZero: false }, splitLine: { show: false }, min: "dataMin", max: "dataMax"
    }];
    var yAxes = [{ scale: true, splitArea: { show: true } }];

    var top = 5 + mainH + 5;
    subCharts.forEach(function (sub, i) {
        grids.push({ left: "5%", right: "5%", top: top + "%", height: subH + "%" });
        xAxes.push({ type: "category", gridIndex: i + 1, data: dates, axisLabel: { show: i === subCount - 1 } });
        yAxes.push({ gridIndex: i + 1, splitNumber: 3, axisLabel: { show: false }, axisTick: { show: false }, splitLine: { show: false } });
        top += subH + 5;
    });

    var upColor = "#ec0000", downColor = "#00da3c";
    var series = [{
        name: "K", type: "candlestick", data: ohlc,
        itemStyle: { color: upColor, color0: downColor, borderColor: "#8A0000", borderColor0: "#008F28" }
    }];

    var ci = 0;
    overlays.forEach(function (ov) {
        var c = INDICATOR_COLORS[ci++ % INDICATOR_COLORS.length];
        series.push({
            name: ov.name || "", type: ov.type || "line",
            data: ov.data || [], showSymbol: false,
            lineStyle: { width: 1, color: c }, itemStyle: { color: c }
        });
    });

    if (marks.length > 0) {
        series.push({
            name: "marks", type: "scatter", data: marks.map(function (m) {
                return {
                    value: [m.coord[0], m.coord[1]],
                    label: {
                        show: true, position: m.position || "top",
                        formatter: String(m.value || ""), fontSize: 12, fontWeight: "bold",
                        color: m.type === "buy" ? downColor : upColor
                    },
                    itemStyle: { color: "transparent" }, symbol: "circle", symbolSize: 1
                };
            }), symbolSize: 1, z: 10
        });
    }

    subCharts.forEach(function (sub, i) {
        (sub.series || []).forEach(function (s) {
            var c = INDICATOR_COLORS[ci++ % INDICATOR_COLORS.length];
            var item = {
                name: s.name || "", type: s.type || "line",
                xAxisIndex: i + 1, yAxisIndex: i + 1,
                data: s.data || [], showSymbol: false,
                lineStyle: { width: 1, color: c }, itemStyle: { color: c }
            };
            if (s.type === "bar") {
                item.itemStyle = { color: function (p) { return p.value > 0 ? upColor : downColor; } };
            }
            series.push(item);
        });
    });

    var allXIdx = xAxes.map(function (_, i) { return i; });
    chart.setOption({
        tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
        axisPointer: { link: { xAxisIndex: "all" } },
        grid: grids, xAxis: xAxes, yAxis: yAxes, series: series,
        dataZoom: [
            { type: "inside", xAxisIndex: allXIdx, start: 50, end: 100 },
            { show: true, xAxisIndex: allXIdx, type: "slider", top: "95%", start: 50, end: 100 }
        ]
    }, true);
}

function loadStrategyList() {
    $.getJSON("/api/strategies", function (strategies) {
        var select = $("#strategy-selector");
        select.empty().append('<option value="" disabled>选择实例...</option>');
        strategies.forEach(function (v) {
            var selected = v === currentVariant ? "selected" : "";
            select.append('<option value="' + v + '" ' + selected + '>' + v + '</option>');
        });
    }).fail(function () {
        console.log("cannot load strategy list");
    });
}
