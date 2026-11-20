/*
 * GitHub Pages 静态筛选器。
 * Python 在构建时写入 JSON，本文件只负责浏览器端筛选、评分和渲染。
 */

const state = {
    items: [],
    generatedAt: null,
    lastRun: null,
    currentPage: 1,
};
const PAGE_SIZE = 20;
const MAX_ITEMS_PER_SOURCE_PER_PAGE = 6;
const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
});
const DATE_ONLY_FORMATTER = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
});

const elements = {
    keyword: document.querySelector("#keyword"),
    days: document.querySelector("#days"),
    specificDate: document.querySelector("#specific-date"),
    contentKind: document.querySelector("#content-kind"),
    sortBy: document.querySelector("#sort-by"),
    filterForm: document.querySelector("#filter-form"),
    list: document.querySelector("#news-list"),
    empty: document.querySelector("#empty-state"),
    summary: document.querySelector("#result-summary"),
    total: document.querySelector("#total-count"),
    generatedAt: document.querySelector("#generated-at"),
    syncState: document.querySelector("#sync-state"),
    syncText: document.querySelector("#sync-text"),
    pagination: document.querySelector("#pagination"),
    pagePrev: document.querySelector("#page-prev"),
    pageNext: document.querySelector("#page-next"),
    pageNumbers: document.querySelector("#page-numbers"),
};

function formatTime(value) {
    if (!value) return "时间未知";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "时间未知";
    return DATE_TIME_FORMATTER.format(date);
}

function safeExternalUrl(value) {
    try {
        const url = new URL(value);
        return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch {
        return "";
    }
}

function nextScheduledRefresh() {
    const now = new Date();
    const candidates = [];
    for (let offset = 0; offset <= 2; offset += 1) {
        const midnight = new Date(Date.UTC(
            now.getUTCFullYear(),
            now.getUTCMonth(),
            now.getUTCDate() + offset,
            0,
            0,
            0
        ));
        // 北京时间 12:00 和次日 00:00 对应 UTC 04:00 和 16:00。
        // 页面展示的是任务完成后可见更新的时间，因此同时加上 7 小时。
        candidates.push(new Date(midnight.getTime() + 11 * 3600000));
        candidates.push(new Date(midnight.getTime() + 23 * 3600000));
    }
    const availableAt =
        candidates.find((candidate) => candidate > now) || candidates.at(-1);
    return availableAt;
}

function recencyScore(publishTime, now) {
    if (!publishTime) return 0;
    const published = new Date(publishTime);
    if (Number.isNaN(published.getTime())) return 0;
    const hours = Math.max(0, (now - published) / 3600000);
    return Math.max(0, Math.round(100 * (1 - hours / 72)));
}

function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function matchesSearchTerm(text, term) {
    if (/[\u3400-\u9fff]/.test(term)) {
        return text.includes(term);
    }
    const words = term
        .split(/\s+/)
        .filter(Boolean)
        .map(escapeRegExp);
    if (!words.length) return true;
    // Git 可以命中 GitHub；digital 中间的 git 因为前面是字母而不会命中。
    return new RegExp(
        `(?:^|[^a-z0-9])${words.join("\\s+")}`,
        "i"
    ).test(text);
}

function itemSearchText(item) {
    return [
        item.title || "",
        item.title_zh || "",
        item.summary || "",
        item.source || "",
        item.display_source || "",
    ].join(" ").toLocaleLowerCase();
}

function sourceGroup(item) {
    if (item.category === "搜狗微信") return "搜狗微信";
    if (String(item.source || "").toLowerCase().startsWith("github")) {
        return "GitHub";
    }
    return item.source || "未知来源";
}

function balanceSourceDiversity(items) {
    let remaining = [...items];
    const balanced = [];
    while (remaining.length) {
        const selected = [];
        const deferred = [];
        const counts = new Map();
        let consumed = 0;

        for (let index = 0; index < remaining.length; index += 1) {
            if (selected.length >= PAGE_SIZE) {
                consumed = index;
                break;
            }
            const item = remaining[index];
            const group = sourceGroup(item);
            const count = counts.get(group) || 0;
            if (count < MAX_ITEMS_PER_SOURCE_PER_PAGE) {
                selected.push(item);
                counts.set(group, count + 1);
            } else {
                deferred.push(item);
            }
        }
        if (consumed === 0) {
            consumed = remaining.length;
        }

        const fillCount = Math.min(
            PAGE_SIZE - selected.length,
            deferred.length
        );
        selected.push(...deferred.slice(0, fillCount));
        balanced.push(...selected);
        remaining = [
            ...deferred.slice(fillCount),
            ...remaining.slice(consumed),
        ];
    }
    return balanced;
}

function compareRankedItems(left, right, sortBy) {
    if (sortBy === "heat") {
        const heatOrder = right.heat_score - left.heat_score;
        if (heatOrder !== 0) return heatOrder;
    } else if (sortBy === "relevance") {
        const crossOrder =
            Number(Boolean(right.is_ai_music_cross))
            - Number(Boolean(left.is_ai_music_cross));
        if (crossOrder !== 0) return crossOrder;
        const relevanceOrder =
            right.relevance_score - left.relevance_score;
        if (relevanceOrder !== 0) return relevanceOrder;
    }
    const timeOrder = String(right.publish_time || "").localeCompare(
        String(left.publish_time || "")
    );
    if (timeOrder !== 0) return timeOrder;
    return right.rank_score - left.rank_score;
}

function rankItems() {
    const days = Number(elements.days.value);
    const specificDate = elements.specificDate.value;
    const contentKind = elements.contentKind.value;
    const sortBy = elements.sortBy.value;
    const terms = elements.keyword.value
        .toLocaleLowerCase()
        .split(/[;；]/)
        .map((term) => term.trim())
        .filter(Boolean);
    const now = Date.now();
    const todayDate = shanghaiDate(new Date(now).toISOString());
    let startDate = "";
    if (days > 0) {
        const startInstant = new Date(`${todayDate}T00:00:00+08:00`);
        startInstant.setUTCDate(startInstant.getUTCDate() - (days - 1));
        startDate = shanghaiDate(startInstant.toISOString());
    }

    const sortedItems = state.items
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
            } else if (days > 0) {
                const itemDate = shanghaiDate(item.publish_time);
                if (
                    Number.isNaN(publishTimestamp)
                    || !itemDate
                    || itemDate < startDate
                    || itemDate > todayDate
                ) {
                    return false;
                }
            }
            if (
                isEnglishTitle(item.title || "")
                && (!item.title_zh || item.title_zh === "None")
            ) {
                return false;
            }
            if (contentKind === "hardware" && !item.is_hardware) {
                return false;
            }
            if (contentKind === "software" && !item.is_software) {
                return false;
            }
            const text = itemSearchText(item);
            return (
                terms.length === 0
                || terms.some((term) => matchesSearchTerm(text, term))
            );
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
            return compareRankedItems(left, right, sortBy);
        });
    return balanceSourceDiversity(sortedItems);
}

function shanghaiDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const parts = DATE_ONLY_FORMATTER.formatToParts(date);
    const part = (type) => parts.find((entry) => entry.type === type)?.value;
    return `${part("year")}-${part("month")}-${part("day")}`;
}

function isEnglishTitle(title) {
    const cjk = (title.match(/[\u3400-\u9fff]/g) || []).length;
    const latin = (title.match(/[A-Za-z]/g) || []).length;
    return latin >= 10 && cjk < 2;
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
    const sourceName = createCell(
      "source-name",
      item.display_source || item.source || "未知来源",
    );
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

function createPageButton(pageNumber, currentPage) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "page-button";
    button.textContent = String(pageNumber);
    if (pageNumber === currentPage) {
        button.classList.add("current");
        button.setAttribute("aria-current", "page");
    }
    button.addEventListener("click", () => {
        state.currentPage = pageNumber;
        render();
    });
    return button;
}

function renderPagination(totalPages) {
    const currentPage = state.currentPage;
    const firstPage = Math.max(1, currentPage - 2);
    const lastPage = Math.min(totalPages, currentPage + 2);
    const controls = [];

    if (firstPage > 1) {
        controls.push(createPageButton(1, currentPage));
        if (firstPage > 2) {
            controls.push(createCell("page-ellipsis", "…"));
        }
    }
    for (let page = firstPage; page <= lastPage; page += 1) {
        controls.push(createPageButton(page, currentPage));
    }
    if (lastPage < totalPages) {
        if (lastPage < totalPages - 1) {
            controls.push(createCell("page-ellipsis", "…"));
        }
        controls.push(createPageButton(totalPages, currentPage));
    }

    elements.pageNumbers.replaceChildren(...controls);
    elements.pagePrev.disabled = currentPage <= 1;
    elements.pageNext.disabled = currentPage >= totalPages;
}

function render() {
    const ranked = rankItems();
    const totalPages = Math.max(1, Math.ceil(ranked.length / PAGE_SIZE));
    state.currentPage = Math.min(state.currentPage, totalPages);
    const pageStart = (state.currentPage - 1) * PAGE_SIZE;
    const visibleItems = ranked.slice(pageStart, pageStart + PAGE_SIZE);
    elements.list.replaceChildren();
    visibleItems.forEach((item, index) => {
        elements.list.append(renderRow(item, pageStart + index + 1));
    });

    elements.empty.hidden = ranked.length > 0;
    const days = Number(elements.days.value);
    const specificDate = elements.specificDate.value;
    const contentKind = elements.contentKind.value;
    const sortBy = elements.sortBy.value;
    const keyword = elements.keyword.value.trim();
    elements.summary.textContent = [
        `${ranked.length} 条结果`,
        specificDate || (days ? `最近 ${days} 天` : "全部时间"),
        contentKind === "hardware"
            ? "硬件相关"
            : contentKind === "software"
                ? "软件相关"
                : "",
        sortBy === "heat"
            ? "按热度"
            : sortBy === "relevance"
                ? "按 AI+音乐关联度"
                : "",
        keyword ? `关键词“${keyword}”` : "",
    ].filter(Boolean).join(" · ");
    elements.pagination.hidden = totalPages <= 1;
    renderPagination(totalPages);
}

async function loadData() {
    try {
        const response = await fetch("./data/news.json", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        state.items = Array.isArray(payload.items)
            ? payload.items.filter((item) => safeExternalUrl(item.link))
            : [];
        state.generatedAt = payload.generated_at;
        state.lastRun = payload.last_run;

        elements.total.textContent = String(state.items.length);
        elements.generatedAt.textContent = formatTime(payload.generated_at);
        const generatedTime = new Date(payload.generated_at).getTime();
        const ageHours = Number.isFinite(generatedTime)
            ? Math.max(0, (Date.now() - generatedTime) / 3600000)
            : Infinity;
        elements.syncState.className = ageHours > 30
            ? "sync-state offline"
            : "sync-state online";
        const estimatedLine = document.createElement("span");
        estimatedLine.textContent =
            `预计下次刷新时间：${formatTime(nextScheduledRefresh().toISOString())}`;
        const delayNote = document.createElement("small");
        delayNote.className = "sync-note";
        delayNote.textContent = ageHours > 30
            ? "最近一次自动更新可能失败，当前显示上一版数据"
            : ageHours > 24
                ? "数据更新可能延迟"
                : "实际刷新时间存在偏差";
        elements.syncText.replaceChildren(estimatedLine, delayNote);
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
    state.currentPage = 1;
    render();
});
elements.days.addEventListener("change", () => {
    elements.specificDate.value = "";
    state.currentPage = 1;
    render();
});
elements.specificDate.addEventListener("change", () => {
    state.currentPage = 1;
    render();
});
elements.contentKind.addEventListener("change", () => {
    state.currentPage = 1;
    render();
});
elements.sortBy.addEventListener("change", () => {
    state.currentPage = 1;
    render();
});
let searchTimer = null;
elements.keyword.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
        state.currentPage = 1;
        render();
    }, 200);
});
elements.pagePrev.addEventListener("click", () => {
    state.currentPage = Math.max(1, state.currentPage - 1);
    render();
});
elements.pageNext.addEventListener("click", () => {
    state.currentPage += 1;
    render();
});

loadData();
