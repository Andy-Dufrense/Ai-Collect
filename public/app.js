/*
 * GitHub Pages 静态筛选器。
 * Python 在构建时写入 JSON，本文件只负责浏览器端筛选、评分和渲染。
 */

const state = {
    items: [],
    generatedAt: null,
    lastRun: null,
};

const elements = {
    keyword: document.querySelector("#keyword"),
    days: document.querySelector("#days"),
    filterForm: document.querySelector("#filter-form"),
    list: document.querySelector("#news-list"),
    empty: document.querySelector("#empty-state"),
    summary: document.querySelector("#result-summary"),
    total: document.querySelector("#total-count"),
    generatedAt: document.querySelector("#generated-at"),
    syncState: document.querySelector("#sync-state"),
    syncText: document.querySelector("#sync-text"),
    diagnostic: document.querySelector("#diagnostic"),
    diagnosticSummary: document.querySelector("#diagnostic-summary"),
    diagnosticErrors: document.querySelector("#diagnostic-errors"),
};

function formatTime(value) {
    if (!value) return "时间未知";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "时间未知";
    return new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    }).format(date);
}

function recencyScore(publishTime, now) {
    if (!publishTime) return 0;
    const published = new Date(publishTime);
    if (Number.isNaN(published.getTime())) return 0;
    const hours = Math.max(0, (now - published) / 3600000);
    return Math.max(0, Math.round(100 * (1 - hours / 72)));
}

function rankItems() {
    const days = Number(elements.days.value);
    const terms = elements.keyword.value
        .toLocaleLowerCase()
        .split(/\s+/)
        .filter(Boolean);
    const now = Date.now();
    const cutoff = days > 0 ? now - days * 86400000 : null;

    return state.items
        .filter((item) => {
            const publishTimestamp = item.publish_time
                ? new Date(item.publish_time).getTime()
                : NaN;
            if (cutoff !== null) {
                if (Number.isNaN(publishTimestamp) || publishTimestamp < cutoff) {
                    return false;
                }
            }
            const text = `${item.title || ""} ${item.summary || ""}`.toLocaleLowerCase();
            return terms.every((term) => text.includes(term));
        })
        .map((item) => {
            const recency = recencyScore(item.publish_time, now);
            return {
                ...item,
                recency_score: recency,
                rank_score: Math.round(
                    item.relevance_score * 0.5
                    + item.heat_score * 0.3
                    + recency * 0.2
                ) / 10,
            };
        })
        .sort((left, right) => {
            if (right.rank_score !== left.rank_score) {
                return right.rank_score - left.rank_score;
            }
            return String(right.publish_time || "").localeCompare(
                String(left.publish_time || "")
            );
        });
}

function createCell(className, text) {
    const element = document.createElement("span");
    element.className = className;
    element.textContent = text;
    return element;
}

function renderRow(item, rank) {
    const row = document.createElement("article");
    row.className = "feed-row";

    const rankCell = createCell(
        `rank-number${rank <= 3 ? " top-rank" : ""}`,
        String(rank)
    );
    const titleLink = document.createElement("a");
    titleLink.className = "feed-title";
    titleLink.href = item.link;
    titleLink.target = "_blank";
    titleLink.rel = "noopener noreferrer";
    titleLink.title = item.title;
    titleLink.textContent = item.title;

    const sourceCell = document.createElement("span");
    sourceCell.className = "feed-source";
    const category = createCell("category-tag", item.category || "RSS");
    const sourceName = createCell("source-name", item.source || "未知来源");
    sourceCell.append(category, sourceName);

    const relevance = createCell("metric", String(item.relevance_score));
    const heat = createCell("metric", String(item.heat_score));
    const publishTime = document.createElement("time");
    publishTime.className = "publish-time";
    publishTime.dateTime = item.publish_time || "";
    publishTime.textContent = formatTime(item.publish_time);

    row.append(
        rankCell,
        titleLink,
        sourceCell,
        relevance,
        heat,
        publishTime
    );
    return row;
}

function render() {
    const ranked = rankItems();
    elements.list.replaceChildren();
    ranked.forEach((item, index) => {
        elements.list.append(renderRow(item, index + 1));
    });

    elements.empty.hidden = ranked.length > 0;
    const days = Number(elements.days.value);
    const keyword = elements.keyword.value.trim();
    elements.summary.textContent = [
        `${ranked.length} 条结果`,
        days ? `最近 ${days} 天` : "全部时间",
        keyword ? `关键词“${keyword}”` : "",
    ].filter(Boolean).join(" · ");
}

function renderDiagnostics() {
    const lastRun = state.lastRun;
    if (!lastRun || !lastRun.failed_sources || !lastRun.errors?.length) return;
    elements.diagnostic.hidden = false;
    elements.diagnosticSummary.textContent = `来源状态：${lastRun.successful_sources}/${lastRun.source_count} 成功`;
    elements.diagnosticErrors.replaceChildren();
    lastRun.errors.forEach((error) => {
        const item = document.createElement("li");
        item.textContent = error;
        elements.diagnosticErrors.append(item);
    });
}

async function loadData() {
    try {
        const response = await fetch("./data/news.json", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        state.items = Array.isArray(payload.items) ? payload.items : [];
        state.generatedAt = payload.generated_at;
        state.lastRun = payload.last_run;

        elements.total.textContent = String(payload.total ?? state.items.length);
        elements.generatedAt.textContent = formatTime(payload.generated_at);
        elements.syncState.className = "sync-state online";
        elements.syncText.textContent = "Actions 自动更新 · 12 小时";
        renderDiagnostics();
        render();
    } catch (error) {
        elements.syncState.className = "sync-state offline";
        elements.syncText.textContent = "数据加载失败";
        elements.summary.textContent = `无法读取 news.json：${error.message}`;
        elements.empty.hidden = false;
    }
}

elements.filterForm.addEventListener("submit", (event) => {
    event.preventDefault();
    render();
});
elements.days.addEventListener("change", render);
elements.keyword.addEventListener("input", render);

loadData();
