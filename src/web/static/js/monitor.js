let charts = {}; // 标的 -> echarts 实例
let autoRefreshTimer = null;
let currentVariant = null;
let selectedMonth = "all"; // 当前选中的月份过滤

function initMonitor(variant) {
    currentVariant = variant;
    
    // 加载策略列表用于选择器
    loadStrategyList();
    
    // 设置自动刷新开关
    $("#auto-refresh-switch").on("change", function() {
        if (this.checked) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });
    
    // 策略选择器
    $("#strategy-selector").on("change", function() {
        const newVariant = $(this).val();
        if (newVariant && newVariant !== currentVariant) {
            window.location.href = `/dashboard/${newVariant}`;
        }
    });

    // 监听月份筛选器点击 (事件委托)
    $("#month-filter-container").on("change", ".btn-check", function() {
        selectedMonth = $(this).val();
        // 立即触发一次渲染以更新显示/隐藏状态
        if (lastData) {
            updateDashboard(lastData);
        }
    });

    // 初始获取
    fetchData();
    startAutoRefresh();
}

let lastData = null; // 缓存最后一次获取的数据

function fetchData() {
    if (!currentVariant) return;
    
    // 添加时间戳防止浏览器缓存
    const timestamp = new Date().getTime();
    $.getJSON(`/api/data/${currentVariant}?t=${timestamp}`, function(data) {
        lastData = data;
        // 简单的时间戳检查以避免不必要的重新渲染
        const lastTs = $("#last-update").text();
        if (lastTs && data.timestamp === lastTs) {
            // 数据没变，但我们可能需要切换月份筛选，所以继续执行 updateDashboard
            // updateDashboard 内部会有更细致的判断
        }
        updateDashboard(data);
    }).fail(function() {
        console.log("获取数据失败");
    });
}

function updateDashboard(data) {
    $("#last-update").text(data.timestamp);
    
    // 更新表格
    updateTables(data.positions, data.orders);
    
    // 更新月份筛选按钮
    updateMonthButtons(data.instruments);
    
    // 更新图表
    const container = $("#charts-area");
    // 如果是首次加载，清除加载动画
    if (container.find(".spinner-border").length > 0) {
        container.empty();
    }
    
    // 遍历标的
    const symbols = Object.keys(data.instruments);
    if (symbols.length === 0) {
        if (container.children().length === 0)
            container.html('<div class="alert alert-info">暂无标的数据。</div>');
        return;
    }

    symbols.forEach(symbol => {
        const inst = data.instruments[symbol];
        const chartId = `chart-${symbol.replace(/[\.\/]/g, '-')}`;
        const wrapperId = `wrapper-${chartId}`;
        
        // 过滤判断
        const isVisible = (selectedMonth === "all" || inst.delivery_month === selectedMonth);

        // 如果不存在则创建容器
        if ($(`#${chartId}`).length === 0) {
            const html = `
                <div id="${wrapperId}" class="mb-4 instrument-wrapper">
                    <div class="instrument-header">
                        <h5 class="mb-0">${symbol} <small class="text-muted" style="font-size: 0.6em;">(${inst.delivery_month})</small></h5>
                        <div id="status-${chartId}"></div>
                    </div>
                    <div id="${chartId}" class="chart-container" style="height: 600px;"></div>
                </div>
            `;
            container.append(html);
            charts[symbol] = echarts.init(document.getElementById(chartId));
            
            // 处理窗口大小调整
            window.addEventListener('resize', function() {
                charts[symbol].resize();
            });
        }
        
        // 控制显示/隐藏
        const wrapper = $(`#${wrapperId}`);
        if (isVisible) {
            wrapper.show();
            renderChart(charts[symbol], symbol, inst);
            updateStatusBadges(chartId, inst.status);
        } else {
            wrapper.hide();
        }
    });
}

function updateMonthButtons(instruments) {
    const months = new Set();
    Object.values(instruments).forEach(inst => {
        if (inst.delivery_month) months.add(inst.delivery_month);
    });
    
    const sortedMonths = Array.from(months).sort();
    const container = $("#month-filter-container");
    
    // 检查是否需要更新按钮（避免每次刷新都闪烁）
    const existingButtons = container.find(".btn-check").length - 1; // 减去 "all"
    if (existingButtons === sortedMonths.length) return; 

    // 保留 "全部" 按钮
    const allBtn = container.find("#month-all").parent().prevObject.filter("#month-all");
    const allLabel = container.find("label[for='month-all']");
    container.empty();
    container.append(allBtn).append(allLabel);

    sortedMonths.forEach(m => {
        const id = `month-${m}`;
        const checked = (selectedMonth === m) ? "checked" : "";
        const html = `
            <input type="radio" class="btn-check" name="month-radio" id="${id}" value="${m}" ${checked}>
            <label class="btn btn-outline-primary" for="${id}">${m}</label>
        `;
        container.append(html);
    });
}

function updateTables(positions, orders) {
    const posBody = $("#positions-table tbody");
    posBody.empty();
    if (positions.length === 0) {
        posBody.append('<tr><td colspan="4" class="text-center text-muted">无持仓</td></tr>');
    } else {
        positions.forEach(p => {
            const row = `<tr>
                <td>${p.vt_symbol}</td>
                <td>${p.direction}</td>
                <td>${p.volume}</td>
                <td>${p.pnl ? p.pnl.toFixed(2) : '0.00'}</td>
            </tr>`;
            posBody.append(row);
        });
    }
    
    const ordBody = $("#orders-table tbody");
    ordBody.empty();
    if (orders.length === 0) {
        ordBody.append('<tr><td colspan="4" class="text-center text-muted">无活动订单</td></tr>');
    } else {
        orders.forEach(o => {
            // ID 方向 价格 状态
            const row = `<tr>
                <td title="${o.vt_orderid}">${o.vt_orderid.split('.')[0]}</td>
                <td>${o.direction}</td>
                <td>${o.price}</td>
                <td>${o.status}</td>
            </tr>`;
            ordBody.append(row);
        });
    }
}

function updateStatusBadges(chartId, status) {
    const container = $(`#status-${chartId}`);
    let html = '';
    
    if (status.dull_top) html += '<span class="badge bg-warning text-dark status-badge">顶部钝化</span>';
    if (status.dull_bottom) html += '<span class="badge bg-warning text-dark status-badge">底部钝化</span>';
    if (status.div_top) html += '<span class="badge bg-danger status-badge">顶部背离确认</span>';
    if (status.div_bottom) html += '<span class="badge bg-success status-badge">底部背离确认</span>';
    if (status.div_top_potential) html += '<span class="badge bg-secondary status-badge">潜在顶部背离</span>';
    if (status.div_bottom_potential) html += '<span class="badge bg-secondary status-badge">潜在底部背离</span>';
    
    container.html(html);
}

function renderChart(chart, symbol, data) {
    const dates = data.dates;
    const ohlc = data.ohlc;
    const volumes = data.volumes;
    const macd = data.macd;
    const td_marks = data.td_marks || [];
    
    // 计算 K 线颜色
    const upColor = '#ec0000';
    const upBorderColor = '#8A0000';
    const downColor = '#00da3c';
    const downBorderColor = '#008F28';

    // 准备 TD 标记数据
    const tdSeriesData = td_marks.map(m => {
        return {
            value: [m.coord[0], m.coord[1]], 
            label: {
                show: true,
                position: m.position, // 'top' or 'bottom'
                formatter: m.value + '',
                fontSize: 12,
                fontWeight: 'bold',
                color: m.type === 'buy' ? downColor : upColor // 对比色
            },
            itemStyle: {
                color: 'transparent' 
            },
            symbol: 'circle',
            symbolSize: 1
        };
    });

    // 准备 MACD 标记点
    const macdMarkData = [];
    if (dates.length > 0) {
        const lastDate = dates[dates.length - 1];
        const lastMacd = macd.hist[macd.hist.length - 1];
        
        if (data.status.div_top) {
            macdMarkData.push({
                coord: [lastDate, lastMacd],
                value: '顶背离',
                itemStyle: { color: downColor }
            });
        }
        if (data.status.div_bottom) {
            macdMarkData.push({
                coord: [lastDate, lastMacd],
                value: '底背离',
                itemStyle: { color: upColor }
            });
        }
    }

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' }
        },
        axisPointer: { link: { xAxisIndex: 'all' } },
        grid: [
            { left: '5%', right: '5%', top: '5%', height: '55%' },
            { left: '5%', right: '5%', top: '65%', height: '20%' }, // MACD
            // 成交量隐藏或合并？计划说 2 个网格，让我们保持成交量小或移除如果不重要
            // 让我们保持成交量叠加或在底部小显示
            // 重新调整计划：网格 1 (K线 + 信号), 网格 2 (MACD)
        ],
        xAxis: [
            {
                type: 'category',
                data: dates,
                scale: true,
                boundaryGap: false,
                axisLine: { onZero: false },
                splitLine: { show: false },
                min: 'dataMin',
                max: 'dataMax'
            },
            {
                type: 'category',
                gridIndex: 1,
                data: dates,
                axisLabel: { show: false }
            }
        ],
        yAxis: [
            { scale: true, splitArea: { show: true } },
            { gridIndex: 1, splitNumber: 3, axisLabel: { show: false }, axisTick: { show: false }, splitLine: { show: false } }
        ],
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
            { show: true, xAxisIndex: [0, 1], type: 'slider', top: '95%', start: 50, end: 100 }
        ],
        series: [
            {
                name: 'K线',
                type: 'candlestick',
                data: ohlc,
                itemStyle: {
                    color: upColor,
                    color0: downColor,
                    borderColor: upBorderColor,
                    borderColor0: downBorderColor
                }
            },
            // TD 设置序列 (散点)
            {
                name: 'TD 结构',
                type: 'scatter',
                data: tdSeriesData,
                symbolSize: 1, // 隐藏点
                z: 10 // 确保存显示在最上层
            },
            // MACD 序列
            {
                name: 'MACD',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: macd.hist,
                itemStyle: {
                    color: function(params) {
                        return params.value > 0 ? upColor : downColor;
                    }
                },
                markPoint: {
                    data: macdMarkData,
                    symbol: 'pin',
                    symbolSize: 30,
                    label: { fontSize: 8 }
                }
            },
            {
                name: 'Diff',
                type: 'line',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: macd.diff,
                lineStyle: { width: 1, color: '#ff9800' }
            },
            {
                name: 'Dea',
                type: 'line',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: macd.dea,
                lineStyle: { width: 1, color: '#2196f3' }
            }
        ]
    };
    
    // 保持缩放状态如果图表已存在
    // (ECharts setOption 默认 notMerge=false 应该能处理数据更新同时保持缩放，如果数据长度匹配或追加)
    // 但如果我们替换数据，可能会丢失缩放。
    // 理想情况下应该使用 'dataZoom' 事件保存状态。
    // 为了简单起见，我们直接 setOption。ECharts 5 通常足够智能。

    chart.setOption(option);
}

// 辅助函数：加载策略列表
function loadStrategyList() {
    $.getJSON("/", function(html) {
        // 这有点黑客做法，因为 "/" 返回 HTML 页面
        // 但我们可以解析它，或者更好的是添加一个 API
        // 目前，让我们尝试通过专用 API 端点获取策略列表
        // 如果不可用，我们依赖用户手动在 URL 中输入变体或回退
        
        // 让我们在 app.py 中实现一个简单的 API 调用来获取列表
        // 或者解析 HTML。
        // 解析 HTML:
        const doc = new DOMParser().parseFromString(html, "text/html");
        const links = doc.querySelectorAll(".list-group-item");
        const select = $("#strategy-selector");
        select.empty();
        select.append('<option value="" disabled>选择策略...</option>');
        
        links.forEach(link => {
            const href = link.getAttribute("href"); // /dashboard/15m
            if (href && href.startsWith("/dashboard/")) {
                const variant = href.split("/").pop();
                const selected = variant === currentVariant ? "selected" : "";
                select.append(`<option value="${variant}" ${selected}>${variant}</option>`);
            }
        });
    }).fail(function() {
        // 如果索引不可访问的回退
        console.log("无法加载策略列表");
    });
}
