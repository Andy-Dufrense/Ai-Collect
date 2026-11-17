/*
 * 本地 Flask 页面交互：
 * - 默认只显示 20 条，点击一次增加 20 条；
 * - 时间范围、指定日期和搜索词改变后自动刷新，不再需要“筛选”按钮。
 */

const PAGE_SIZE = 20;
const newsRows = Array.from(document.querySelectorAll(".feed-row"));
const loadMoreButton = document.querySelector("#load-more");
const loadStatus = document.querySelector("#load-status");
const filterForm = document.querySelector("#filter-form");
const daysFilter = document.querySelector("#days-filter");
const dateFilter = document.querySelector("#date-filter");
const searchInput = document.querySelector(".search-field input");
let visibleCount = Math.min(PAGE_SIZE, newsRows.length);

function updateVisibleRows() {
    newsRows.forEach((row, index) => {
        row.hidden = index >= visibleCount;
    });
    if (loadMoreButton) {
        loadMoreButton.hidden = visibleCount >= newsRows.length;
    }
    if (loadStatus) {
        loadStatus.textContent = newsRows.length
            ? `已显示 ${Math.min(visibleCount, newsRows.length)} / ${newsRows.length} 条`
            : "";
    }
}

loadMoreButton?.addEventListener("click", () => {
    visibleCount += PAGE_SIZE;
    updateVisibleRows();
});

function submitFilters() {
    filterForm?.requestSubmit();
}

daysFilter?.addEventListener("change", () => {
    if (dateFilter) dateFilter.value = "";
    submitFilters();
});
dateFilter?.addEventListener("change", submitFilters);

let searchTimer = null;
searchInput?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(submitFilters, 600);
});

updateVisibleRows();
