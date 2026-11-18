/*
 * 本地 Flask 页面交互：
 * 时间范围、指定日期和搜索词改变后自动刷新，不再需要“筛选”按钮。
 * 分页由 Flask 服务端完成，每页固定 20 条。
 */

const filterForm = document.querySelector("#filter-form");
const daysFilter = document.querySelector("#days-filter");
const dateFilter = document.querySelector("#date-filter");
const contentKindFilter = document.querySelector("#content-kind-filter");
const searchInput = document.querySelector(".search-field input");

function submitFilters() {
    filterForm?.requestSubmit();
}

daysFilter?.addEventListener("change", () => {
    if (dateFilter) dateFilter.value = "";
    submitFilters();
});
dateFilter?.addEventListener("change", submitFilters);
contentKindFilter?.addEventListener("change", submitFilters);

let searchTimer = null;
searchInput?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(submitFilters, 600);
});
