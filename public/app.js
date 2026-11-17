/*
 * GitHub Pages 静态筛选器。
 * Python 在构建时写入 JSON，本文件只负责浏览器端筛选、评分和渲染。
 */

const state = {
    items: [],
    generatedAt: null,
    lastRun: null,
    visibleCount: 20,
};
const PAGE_SIZE = 20;

const elements = {
    keyword: document.querySelector("#keyword"),
    days: document.querySelector("#days"),
    specificDate: document.querySelector("#specific-date"),
    filterForm: document.querySelector("#filter-form"),
    list: document.querySelector("#news-list"),
    empty: document.querySelector("#empty-state"),
    summary: document.querySelector("#result-summary"),
    total: document.querySelector("#total-count"),
    generatedAt: document.querySelector("#generated-at"),
    syncState: document.querySelector("#sync-state"),
    syncText: document.querySelector("#sync-text"),
    loadMore: document.querySelector("#load-more"),
    loadStatus: document.querySelector("#load-status"),
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

function nextScheduledRefresh() {
    const now = new Date();
    const candidates = [];
    for (let offset = 0; offset <= 1; offset += 1) {
        const midnight = new Date(Date.UTC(
            now.getUTCFullYear(),
            now.getUTCMonth(),
            now.getUTCDate() + offset,
            0,
            0,
            0
        ));
        candidates.push(midnight);
        candidates.push(new Date(midnight.getTime() + 12 * 3600000));
    }
    return candidates.find((candidate) => candidate > now) || candidates.at(-1);
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
    const specificDate = elements.specificDate.value;
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
            if (specificDate) {
                if (
                    Number.isNaN(publishTimestamp)
                    || shanghaiDate(item.publish_time) !== specificDate
                ) {
                    return false;
                }
            } else if (cutoff !== null) {
                if (Number.isNaN(publishTimestamp) || publishTimestamp < cutoff) {
                    return false;
                }
            }
            const text = [
                item.title || "",
                item.title_zh || "",
                item.summary || "",
            ].join(" ").toLocaleLowerCase();
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

function shanghaiDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).formatToParts(date);
    const part = (type) => parts.find((entry) => entry.type === type)?.value;
    return `${part("year")}-${part("month")}-${part("day")}`;
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
    const displayTitle = item.title_zh && item.title_zh !== "None"
        ? item.title_zh
        : item.title;
    titleLink.textContent = displayTitle;

    const sourceCell = document.createElement("span");
    sourceCell.className = "feed-source";
    const category = createCell("category-tag", item.category || "RSS");
    const sourceName = createCell("source-name", item.source || "未知来源");
    sourceCell.append(category, sourceName);

    const publishTime = document.createElement("time");
    publishTime.className = "publish-time";
    publishTime.dateTime = item.publish_time || "";
    publishTime.textContent = formatTime(item.publish_time);

    row.append(
        rankCell,
        titleLink,
        sourceCell,
        publishTime
    );
    return row;
}

function render() {
    const ranked = rankItems();
    const visibleItems = ranked.slice(0, state.visibleCount);
    elements.list.replaceChildren();
    visibleItems.forEach((item, index) => {
        elements.list.append(renderRow(item, index + 1));
    });

    elements.empty.hidden = ranked.length > 0;
    const days = Number(elements.days.value);
    const specificDate = elements.specificDate.value;
    const keyword = elements.keyword.value.trim();
    elements.summary.textContent = [
        `${ranked.length} 条结果`,
        specificDate || (days ? `最近 ${days} 天` : "全部时间"),
        keyword ? `关键词“${keyword}”` : "",
    ].filter(Boolean).join(" · ");
    elements.loadMore.hidden = visibleItems.length >= ranked.length;
    elements.loadStatus.textContent = ranked.length
        ? `已显示 ${visibleItems.length} / ${ranked.length} 条`
        : "";
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
        elements.syncText.textContent =
            `Actions 自动更新 · 下次 ${formatTime(nextScheduledRefresh().toISOString())}`;
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
    state.visibleCount = PAGE_SIZE;
    render();
});
elements.days.addEventListener("change", () => {
    elements.specificDate.value = "";
    state.visibleCount = PAGE_SIZE;
    render();
});
elements.specificDate.addEventListener("change", () => {
    state.visibleCount = PAGE_SIZE;
    render();
});
elements.keyword.addEventListener("input", () => {
    state.visibleCount = PAGE_SIZE;
    render();
});
elements.loadMore.addEventListener("click", () => {
    state.visibleCount += PAGE_SIZE;
    render();
});

loadData();
