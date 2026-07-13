const sourcePath = document.querySelector("#source-path");
const importPathButton = document.querySelector("#import-path");
const uploadInput = document.querySelector("#save-upload");
const autoRefresh = document.querySelector("#auto-refresh");
const status = document.querySelector("#status");
const emptyState = document.querySelector("#empty-state");
const marketContent = document.querySelector("#market-content");
const goodsTable = document.querySelector("#goods-table");
const highlightThresholdInput = document.querySelector("#highlight-threshold");
const chart = document.querySelector("#history-chart");
const chartLegend = document.querySelector("#chart-legend");
const chartTooltip = document.querySelector("#chart-tooltip");
const purchaseCostDialog = document.querySelector("#purchase-cost-dialog");
const purchaseCostForm = document.querySelector("#purchase-cost-form");
const purchaseCostDescription = document.querySelector("#purchase-cost-description");
const purchaseCostInput = document.querySelector("#purchase-cost-input");
const removePurchaseCostButton = document.querySelector("#remove-purchase-cost");
const cancelPurchaseCostButton = document.querySelector("#cancel-purchase-cost");

const sourceStorageKey = "cookie-market.source-path";
const autoRefreshStorageKey = "cookie-market.auto-refresh";
const purchaseCostsStorageKey = "cookie-market.purchase-costs";
const highlightThresholdStorageKey = "cookie-market.highlight-threshold";
const marketModes = [
    { icon: "↔", label: "Stable" },
    { icon: "↗", label: "Slow rise" },
    { icon: "↘", label: "Slow fall" },
    { icon: "↑", label: "Fast rise" },
    { icon: "↓", label: "Fast fall" },
    { icon: "⇅", label: "Chaotic" },
];
const chartColors = [
    "#ffc75b", "#80d297", "#ff8e7f", "#89b4fa", "#cba6f7",
    "#f9e2af", "#94e2d5", "#f5c2e7", "#fab387", "#a6e3a1",
];
let snapshots = [];
let selectedGoodIds = new Set([0]);
let chartGeometry = null;
let highlightedGoodId = null;
let refreshTimer;
let purchaseCosts = loadPurchaseCosts();
let editedPurchaseCostGood = null;

sourcePath.value = localStorage.getItem(sourceStorageKey) || "";
autoRefresh.checked = localStorage.getItem(autoRefreshStorageKey) === "true";
highlightThresholdInput.value = localStorage.getItem(highlightThresholdStorageKey) || "10";

function loadPurchaseCosts() {
    try {
        const costs = JSON.parse(localStorage.getItem(purchaseCostsStorageKey) || "{}");
        return Object.fromEntries(Object.entries(costs).filter(([, value]) =>
            Number.isFinite(value) && value > 0
        ));
    } catch {
        return {};
    }
}

function purchaseCostFor(goodId) {
    return purchaseCosts[goodId];
}

function highlightThreshold() {
    const threshold = Number(highlightThresholdInput.value);
    return Number.isFinite(threshold) && threshold >= 0 ? threshold : 10;
}

function editPurchaseCost(price) {
    const existingCost = purchaseCostFor(price.good_id);
    editedPurchaseCostGood = price;
    purchaseCostDescription.textContent = `Record the price paid for ${price.name}.`;
    purchaseCostInput.value = existingCost?.toFixed(2) || price.price.toFixed(2);
    removePurchaseCostButton.hidden = !existingCost;
    purchaseCostDialog.showModal();
    purchaseCostInput.focus();
}

function savePurchaseCost(cost) {
    purchaseCosts[editedPurchaseCostGood.good_id] = cost;
    localStorage.setItem(purchaseCostsStorageKey, JSON.stringify(purchaseCosts));
    renderTable(latestSnapshot().prices.filter((item) => item.unlocked));
}

function removePurchaseCost() {
    delete purchaseCosts[editedPurchaseCostGood.good_id];
    localStorage.setItem(purchaseCostsStorageKey, JSON.stringify(purchaseCosts));
    purchaseCostDialog.close();
    renderTable(latestSnapshot().prices.filter((item) => item.unlocked));
}

function setStatus(message, tone = "neutral") {
    status.textContent = message;
    status.dataset.tone = tone;
}

async function request(url, options = {}) {
    const response = await fetch(url, options);
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Request failed.");
    return body;
}

async function loadHistory() {
    const body = await request("/api/history");
    snapshots = body.snapshots;
    render();
}

function latestSnapshot() {
    return snapshots.at(-1);
}

function formatTime(value) {
    return new Intl.DateTimeFormat(undefined, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
    }).format(new Date(value));
}

function render() {
    const latest = latestSnapshot();
    emptyState.hidden = Boolean(latest);
    marketContent.hidden = !latest;
    if (!latest) {
        setStatus("No snapshots imported yet.");
        return;
    }

    document.querySelector("#latest-time").textContent = formatTime(latest.captured_at);
    const visiblePrices = latest.prices.filter((price) => price.unlocked);
    document.querySelector("#good-count").textContent = visiblePrices.length;
    document.querySelector("#snapshot-count").textContent = snapshots.length;
    document.querySelector("#game-version").textContent = latest.game_version;

    const visibleIds = new Set(visiblePrices.map((price) => price.good_id));
    selectedGoodIds = new Set([...selectedGoodIds].filter((goodId) => visibleIds.has(goodId)));
    renderTable(visiblePrices);
    renderChart();
    setStatus(`Showing ${snapshots.length} imported ${snapshots.length === 1 ? "snapshot" : "snapshots"}.`, "success");
}

function colorForGood(goodId) {
    return chartColors[goodId % chartColors.length];
}

function renderTable(prices) {
    const threshold = highlightThreshold();
    goodsTable.replaceChildren(...prices.map((price) => {
        const row = document.createElement("tr");
        const purchaseCost = purchaseCostFor(price.good_id);
        const isAboveCost = Number.isFinite(purchaseCost) && price.price > purchaseCost;
        row.className = [
            price.price < threshold && "price-under-threshold",
            isAboveCost && "price-above-cost",
        ].filter(Boolean).join(" ");
        row.style.setProperty("--series-color", colorForGood(price.good_id));
        const observedPrices = snapshots
            .map((snapshot) => snapshot.prices.find((item) => item.good_id === price.good_id)?.price)
            .filter(Number.isFinite);
        const values = [
            price.name,
            `$${price.price.toFixed(2)}`,
            `$${Math.min(...observedPrices).toFixed(2)}`,
            `$${Math.max(...observedPrices).toFixed(2)}`,
            `${price.delta >= 0 ? "+" : ""}${price.delta.toFixed(2)}%`,
            price.inventory.toLocaleString(),
        ];
        values.forEach((value, index) => {
            const cell = document.createElement("td");
            cell.textContent = value;
            if (index === 1 && price.price < threshold) {
                cell.classList.add("low-price");
                cell.title = `Current price is below your $${threshold.toFixed(2)} highlight threshold`;
            }
            if (index === 1 && isAboveCost) {
                cell.title = `Current price is above your $${purchaseCost.toFixed(2)} purchase cost`;
            }
            if (index === 4) cell.className = price.delta >= 0 ? "positive" : "negative";
            row.append(cell);
        });

        const goodCell = row.firstElementChild;
        goodCell.classList.add("good-cell");
        const name = document.createElement("span");
        name.textContent = price.name;
        const costButton = document.createElement("button");
        costButton.className = "purchase-cost-button";
        costButton.type = "button";
        costButton.textContent = purchaseCost ? `✎ $${purchaseCost.toFixed(2)}` : "✎";
        costButton.title = purchaseCost
            ? `Edit $${purchaseCost.toFixed(2)} purchase cost for ${price.name}`
            : `Set purchase cost for ${price.name}`;
        costButton.setAttribute("aria-label", costButton.title);
        costButton.addEventListener("click", (event) => {
            event.stopPropagation();
            editPurchaseCost(price);
        });
        goodCell.replaceChildren(name, costButton);

        const mode = marketModes[price.mode] || { icon: "?", label: "Unknown mode" };
        const modeCell = document.createElement("td");
        const modeIcon = document.createElement("span");
        modeIcon.className = `mode-icon mode-${price.mode}`;
        modeIcon.textContent = mode.icon;
        modeIcon.title = mode.label;
        modeIcon.setAttribute("aria-label", mode.label);
        modeCell.append(modeIcon);
        row.append(modeCell);
        return row;
    }));
}

function toggleGood(goodId) {
    goodId = Number(goodId);
    if (selectedGoodIds.has(goodId)) {
        selectedGoodIds.delete(goodId);
    } else {
        selectedGoodIds.add(goodId);
    }
    const visiblePrices = latestSnapshot().prices.filter((price) => price.unlocked);
    renderTable(visiblePrices);
    renderChart();
}

function seriesForGood(goodId) {
    const good = latestSnapshot().prices.find((price) => price.good_id === goodId);
    return {
        goodId,
        name: good.name,
        color: colorForGood(goodId),
        currentPrice: good.price,
        points: snapshots.map((snapshot, snapshotIndex) => ({
            snapshotIndex,
            time: new Date(snapshot.captured_at),
            price: snapshot.prices.find((price) => price.good_id === goodId)?.price,
        })).filter((point) => Number.isFinite(point.price)),
    };
}

function renderChart() {
    const allSeries = latestSnapshot().prices
        .filter((price) => price.unlocked)
        .map((price) => seriesForGood(price.good_id));
    const series = allSeries.filter((item) => selectedGoodIds.has(item.goodId));
    highlightedGoodId = null;
    chartLegend.replaceChildren(...allSeries.map((item) => {
        const isShown = selectedGoodIds.has(item.goodId);
        const legend = document.createElement("button");
        legend.className = `legend-item${isShown ? "" : " is-hidden"}`;
        legend.type = "button";
        legend.setAttribute("aria-pressed", String(isShown));
        legend.title = `${isShown ? "Hide" : "Show"} ${item.name} on the chart`;
        const swatch = document.createElement("span");
        swatch.className = "series-swatch";
        swatch.style.setProperty("--series-color", item.color);
        const label = document.createElement("span");
        label.append(document.createTextNode(`${item.name} `));
        const price = document.createElement("strong");
        price.textContent = `$${item.currentPrice.toFixed(2)}`;
        label.append(price);
        legend.append(swatch, label);
        const highlight = () => {
            if (!selectedGoodIds.has(item.goodId)) return;
            highlightedGoodId = item.goodId;
            legend.classList.add("highlighted");
            drawChart(series);
        };
        const clearHighlight = () => {
            highlightedGoodId = null;
            legend.classList.remove("highlighted");
            drawChart(series);
        };
        legend.addEventListener("mouseenter", highlight);
        legend.addEventListener("mouseleave", clearHighlight);
        legend.addEventListener("focus", highlight);
        legend.addEventListener("blur", clearHighlight);
        legend.addEventListener("click", () => toggleGood(item.goodId));
        return legend;
    }));
    if (!series.length) {
        document.querySelector("#chart-caption").textContent = "Click a good above to show its price history.";
        drawEmptyChart();
        return;
    }
    const pointCount = Math.max(...series.map((item) => item.points.length));
    document.querySelector("#chart-caption").textContent = pointCount > 1
        ? `${pointCount} imported values. Click a good above to show or hide its line; hover a shown item to highlight it.`
        : "Import more changed saves to build this price history.";

    drawChart(series);
}

function drawEmptyChart() {
    const scale = window.devicePixelRatio || 1;
    const width = chart.clientWidth;
    const height = chart.clientHeight;
    chart.width = Math.round(width * scale);
    chart.height = Math.round(height * scale);
    const context = chart.getContext("2d");
    context.scale(scale, scale);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#b9aa91";
    context.font = "14px system-ui";
    context.textAlign = "center";
    context.fillText("No goods selected", width / 2, height / 2);
    context.textAlign = "left";
    chartGeometry = null;
    chartTooltip.hidden = true;
}

function drawChart(series) {
    const scale = window.devicePixelRatio || 1;
    const width = chart.clientWidth;
    const height = chart.clientHeight;
    chart.width = Math.round(width * scale);
    chart.height = Math.round(height * scale);
    const context = chart.getContext("2d");
    context.scale(scale, scale);
    context.clearRect(0, 0, width, height);

    const padding = { top: 30, right: 22, bottom: 35, left: 54 };
    const usableWidth = width - padding.left - padding.right;
    const usableHeight = height - padding.top - padding.bottom;
    const values = series.flatMap((item) => item.points.map((point) => point.price));
    const low = Math.min(...values);
    const high = Math.max(...values);
    const spread = high - low || Math.max(high * 0.08, 1);
    const lower = Math.max(0, low - spread * 0.18);
    const upper = high + spread * 0.18;
    const x = (snapshotIndex) => padding.left + (snapshots.length === 1 ? usableWidth / 2 : snapshotIndex * usableWidth / (snapshots.length - 1));
    const y = (value) => padding.top + (upper - value) * usableHeight / (upper - lower);

    context.strokeStyle = "rgba(185, 170, 145, .22)";
    context.fillStyle = "#b9aa91";
    context.font = "12px system-ui";
    for (let index = 0; index < 4; index += 1) {
        const value = lower + (upper - lower) * index / 3;
        const lineY = y(value);
        context.beginPath(); context.moveTo(padding.left, lineY); context.lineTo(width - padding.right, lineY); context.stroke();
        context.fillText(`$${value.toFixed(2)}`, 4, lineY + 4);
    }

    const drawOrder = highlightedGoodId === null
        ? series
        : [...series.filter((item) => item.goodId !== highlightedGoodId), ...series.filter((item) => item.goodId === highlightedGoodId)];
    drawOrder.forEach((item) => {
        const highlighted = item.goodId === highlightedGoodId;
        context.save();
        context.globalAlpha = highlightedGoodId === null || highlighted ? 1 : .18;
        context.beginPath();
        item.points.forEach((point, index) => index
            ? context.lineTo(x(point.snapshotIndex), y(point.price))
            : context.moveTo(x(point.snapshotIndex), y(point.price)));
        context.strokeStyle = item.color;
        context.lineWidth = highlighted ? 4 : 2;
        context.shadowColor = highlighted ? item.color : "transparent";
        context.shadowBlur = highlighted ? 8 : 0;
        context.stroke();
        item.points.forEach((point) => {
            context.beginPath();
            context.arc(x(point.snapshotIndex), y(point.price), highlighted ? 4 : 3, 0, Math.PI * 2);
            context.fillStyle = item.color;
            context.fill();
        });
        context.restore();
    });
    const start = new Date(snapshots[0].captured_at).toLocaleDateString();
    const end = new Date(snapshots.at(-1).captured_at).toLocaleDateString();
    context.fillStyle = "#b9aa91";
    context.fillText(start, padding.left, height - 11);
    context.textAlign = "right"; context.fillText(end, width - padding.right, height - 11); context.textAlign = "left";
    chartGeometry = { series, x, y };
    chartTooltip.hidden = true;
}

function showChartTooltip(event) {
    if (!chartGeometry) return;
    const bounds = chart.getBoundingClientRect();
    const pointerX = event.clientX - bounds.left;
    const pointerY = event.clientY - bounds.top;
    let nearest = null;
    chartGeometry.series.forEach((item) => {
        if (item.points.length === 1) {
            const point = item.points[0];
            const pointX = chartGeometry.x(point.snapshotIndex);
            const pointY = chartGeometry.y(point.price);
            const distance = Math.hypot(pointerX - pointX, pointerY - pointY);
            if (!nearest || distance < nearest.distance) nearest = { item, point, pointX, pointY, distance };
            return;
        }
        for (let index = 1; index < item.points.length; index += 1) {
            const start = item.points[index - 1];
            const end = item.points[index];
            const startX = chartGeometry.x(start.snapshotIndex);
            const startY = chartGeometry.y(start.price);
            const endX = chartGeometry.x(end.snapshotIndex);
            const endY = chartGeometry.y(end.price);
            const lengthSquared = (endX - startX) ** 2 + (endY - startY) ** 2;
            const projection = Math.max(0, Math.min(1,
                ((pointerX - startX) * (endX - startX) + (pointerY - startY) * (endY - startY)) / lengthSquared
            ));
            const pointX = startX + projection * (endX - startX);
            const pointY = startY + projection * (endY - startY);
            const distance = Math.hypot(pointerX - pointX, pointerY - pointY);
            const point = projection < .5 ? start : end;
            if (!nearest || distance < nearest.distance) nearest = { item, point, pointX, pointY, distance };
        }
    });
    if (!nearest || nearest.distance > 14) {
        chartTooltip.hidden = true;
        return;
    }
    const name = document.createElement("strong");
    name.textContent = nearest.item.name;
    chartTooltip.replaceChildren(
        name,
        document.createElement("br"),
        document.createTextNode(`$${nearest.point.price.toFixed(2)}`),
        document.createElement("br"),
        document.createTextNode(nearest.point.time.toLocaleString()),
    );
    chartTooltip.style.setProperty("--tooltip-color", nearest.item.color);
    chartTooltip.style.left = `${nearest.pointX}px`;
    chartTooltip.style.top = `${nearest.pointY}px`;
    chartTooltip.hidden = false;
}

async function importFromPath() {
    const path = sourcePath.value.trim();
    if (!path) { setStatus("Enter the complete path to save.txt first.", "error"); return; }
    localStorage.setItem(sourceStorageKey, path);
    setStatus("Reading save…");
    try {
        const result = await request("/api/import-path", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_path: path }) });
        await loadHistory();
        setStatus(result.inserted ? "Saved a new market snapshot." : "That save was already imported.", "success");
    } catch (error) { setStatus(error.message, "error"); }
}

async function importUpload() {
    const file = uploadInput.files[0];
    if (!file) return;
    setStatus(`Uploading ${file.name}…`);
    try {
        const result = await request("/api/import-upload", { method: "POST", headers: { "X-File-Name": encodeURIComponent(file.name) }, body: await file.arrayBuffer() });
        await loadHistory();
        setStatus(result.inserted ? "Saved a new market snapshot." : "That save was already imported.", "success");
    } catch (error) { setStatus(error.message, "error"); }
    uploadInput.value = "";
}

function configureAutoRefresh() {
    clearInterval(refreshTimer);
    localStorage.setItem(autoRefreshStorageKey, autoRefresh.checked);
    if (autoRefresh.checked) refreshTimer = setInterval(importFromPath, 60_000);
}

importPathButton.addEventListener("click", importFromPath);
uploadInput.addEventListener("change", importUpload);
autoRefresh.addEventListener("change", configureAutoRefresh);
highlightThresholdInput.addEventListener("change", () => {
    if (!Number.isFinite(Number(highlightThresholdInput.value)) || Number(highlightThresholdInput.value) < 0) {
        highlightThresholdInput.value = "10";
    }
    localStorage.setItem(highlightThresholdStorageKey, highlightThresholdInput.value);
    if (snapshots.length) renderTable(latestSnapshot().prices.filter((price) => price.unlocked));
});
purchaseCostForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const cost = Number(purchaseCostInput.value);
    if (!Number.isFinite(cost) || cost <= 0) {
        purchaseCostInput.setCustomValidity("Enter a positive purchase price.");
        purchaseCostInput.reportValidity();
        return;
    }
    purchaseCostInput.setCustomValidity("");
    savePurchaseCost(cost);
    purchaseCostDialog.close();
});
purchaseCostInput.addEventListener("input", () => purchaseCostInput.setCustomValidity(""));
removePurchaseCostButton.addEventListener("click", removePurchaseCost);
cancelPurchaseCostButton.addEventListener("click", () => purchaseCostDialog.close());
chart.addEventListener("mousemove", showChartTooltip);
chart.addEventListener("mouseleave", () => { chartTooltip.hidden = true; });
window.addEventListener("resize", () => snapshots.length && renderChart());
configureAutoRefresh();
loadHistory().catch((error) => setStatus(error.message, "error"));