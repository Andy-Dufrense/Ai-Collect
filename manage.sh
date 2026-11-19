#!/usr/bin/env bash

# AI + 音乐资讯系统的一键管理脚本。
#
# 用法：
#   ./manage.sh start    同时启动 Flask 网页和后台自动抓取进程
#   ./manage.sh stop     停止自动抓取和 Flask 网页
#   ./manage.sh restart  重启整个后端
#   ./manage.sh status   查看两个进程及自动同步状态
#   ./manage.sh fetch    手动立即抓取一次
#   ./manage.sh logs     查看网页、自动抓取、手动抓取或翻译日志
#   ./manage.sh review   在终端中审核新闻并调整过滤规则
#   ./manage.sh backfill 按真实发布日期回填最近 60 天
#   ./manage.sh translate 补齐数据库中的英文标题翻译
#
# 启动后后台会立即抓取一次，然后按配置间隔持续轮询 RSS。
# 网页只读取 SQLite，所以日常只需刷新页面，不需要再次点击抓取。

set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${FLASK_HOST:-0.0.0.0}"
PORT="${FLASK_PORT:-5000}"

FLASK_PID_FILE="${PROJECT_DIR}/data/flask.pid"
WORKER_PID_FILE="${PROJECT_DIR}/data/worker.pid"
FLASK_LOG="${PROJECT_DIR}/data/flask.log"
WORKER_LOG="${PROJECT_DIR}/data/worker.log"
FETCH_LOG="${PROJECT_DIR}/data/fetch.log"
TRANSLATION_LOG="${PROJECT_DIR}/data/translation.log"

mkdir -p "${PROJECT_DIR}/data"
cd "${PROJECT_DIR}"

primary_ip() {
    # 取虚拟机第一个非回环 IPv4 地址；没有网络地址时返回“未知”。
    local addresses
    addresses="$(hostname -I 2>/dev/null || true)"
    awk '{print $1}' <<< "${addresses}"
    return 0
}

web_urls() {
    local vm_ip
    vm_ip="$(primary_ip)"
    echo "虚拟机本机：http://127.0.0.1:${PORT}/"
    if [[ -n "${vm_ip}" ]]; then
        echo "Windows 主机：http://${vm_ip}:${PORT}/"
    fi
    return 0
}

# 判断 PID 文件对应的进程是否仍然存在，并检查命令行确实属于目标脚本。
# 这样即使 Linux 复用了旧 PID，也不会误杀一个无关进程。
is_running() {
    local pid_file="$1"
    local expected_script="$2"

    if [[ ! -f "${pid_file}" ]]; then
        return 1
    fi

    local pid
    pid="$(tr -dc '0-9' < "${pid_file}")"
    if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
        rm -f "${pid_file}"
        return 1
    fi

    local command_line=""
    command_line="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
    if [[ "${command_line}" != *"${expected_script}"* ]]; then
        echo "PID ${pid} 不属于 ${expected_script}，已忽略旧 PID 文件。" >&2
        rm -f "${pid_file}"
        return 1
    fi
    return 0
}

web_running() {
    is_running "${FLASK_PID_FILE}" "${PROJECT_DIR}/app.py"
}

worker_running() {
    is_running "${WORKER_PID_FILE}" "${PROJECT_DIR}/auto_fetcher.py"
}

port_in_use() {
    # 检查当前网页端口是否已有程序监听。

    if command -v ss >/dev/null 2>&1; then
        [[ -n "$(ss -H -ltn "sport = :${PORT}" 2>/dev/null)" ]]
        return
    fi

    if command -v fuser >/dev/null 2>&1; then
        fuser -s "${PORT}/tcp" 2>/dev/null
        return
    fi

    return 1
}

listener_pids() {
    # 读取监听网页端口的 PID；没有 ss 或 fuser 时返回空结果。

    if command -v ss >/dev/null 2>&1; then
        ss -H -ltnp "sport = :${PORT}" 2>/dev/null \
            | grep -o 'pid=[0-9]*' \
            | cut -d= -f2 \
            | sort -u
        return
    fi

    if command -v fuser >/dev/null 2>&1; then
        fuser -n tcp "${PORT}" 2>/dev/null \
            | tr ' ' '\n' \
            | tr -dc '0-9\n' \
            | sed '/^$/d' \
            | sort -u
    fi
}

stop_untracked_project_web() {
    # 处理旧版本或手工启动后占用网页端口的本项目 app.py。
    # 只有同时满足“命令行包含 app.py”和“工作目录等于本项目”才会停止，
    # 不会误杀占用 5000 端口的其他软件。

    local pid
    local command_line
    local process_cwd
    local found_pid=0

    while IFS= read -r pid; do
        [[ -n "${pid}" ]] || continue
        command_line="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
        process_cwd="$(readlink "/proc/${pid}/cwd" 2>/dev/null || true)"

        if [[ "${command_line}" == *"app.py"* ]] \
            && [[ "${process_cwd}" == "${PROJECT_DIR}" ]]; then
            echo "发现未记录的旧网页进程 PID ${pid}，正在重启为受管进程。"
            kill "${pid}" 2>/dev/null || true
            found_pid=1
        fi
    done < <(listener_pids)

    if [[ "${found_pid}" -eq 1 ]]; then
        local attempt
        for attempt in {1..20}; do
            if ! port_in_use; then
                return 0
            fi
            sleep 0.5
        done
    fi
    return 0
}

check_proxy_health() {
    # 检查环境变量中的本地 HTTP 代理是否可连接。
    # 这里只给出警告，不阻止网页启动。用户可能稍后才启动代理软件，
    # 网页历史数据仍然可以正常查看。

    local proxy_url="${NEWS_PROXY:-${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}}"
    [[ -n "${proxy_url}" ]] || return 0

    local proxy_host=""
    local proxy_port=""
    if [[ "${proxy_url}" =~ ^[a-zA-Z]+://([^/:]+):([0-9]+) ]]; then
        proxy_host="${BASH_REMATCH[1]}"
        proxy_port="${BASH_REMATCH[2]}"
    fi

    if [[ -n "${proxy_host}" ]] && [[ -n "${proxy_port}" ]]; then
        if timeout 1 bash -c "</dev/tcp/${proxy_host}/${proxy_port}" 2>/dev/null; then
            echo "网络代理可连接：${proxy_host}:${proxy_port}"
        else
            echo "警告：配置了代理 ${proxy_host}:${proxy_port}，但当前无法连接。" >&2
            echo "后台抓取会自动尝试直连；如果必须走代理，请先启动代理软件。" >&2
            echo "也可以清除旧代理变量后重新启动：" >&2
            echo "  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy" >&2
        fi
    fi
}

start_web() {
    if web_running; then
        echo "网页进程已运行，PID: $(cat "${FLASK_PID_FILE}")"
        return 0
    fi

    nohup "${PYTHON_BIN}" "${PROJECT_DIR}/app.py" >> "${FLASK_LOG}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${FLASK_PID_FILE}"

    # 等待片刻，尽早发现端口占用、依赖缺失等启动错误。
    sleep 2
    if ! web_running; then
        rm -f "${FLASK_PID_FILE}"
        echo "网页进程启动失败，最近日志：" >&2
        tail -n 30 "${FLASK_LOG}" >&2 || true
        return 1
    fi

    echo "网页进程已启动，PID: ${pid}"
    web_urls
}

start_worker() {
    if worker_running; then
        echo "自动抓取进程已运行，PID: $(cat "${WORKER_PID_FILE}")"
        return 0
    fi

    nohup "${PYTHON_BIN}" "${PROJECT_DIR}/auto_fetcher.py" >> "${WORKER_LOG}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${WORKER_PID_FILE}"

    # 自动进程会立即抓取，这里只检查进程是否存活，不等待全部网络请求完成。
    sleep 2
    if ! worker_running; then
        rm -f "${WORKER_PID_FILE}"
        echo "自动抓取进程启动失败，最近日志：" >&2
        tail -n 30 "${WORKER_LOG}" >&2 || true
        return 1
    fi

    echo "自动抓取进程已启动，PID: ${pid}"
    echo "自动刷新计划：北京时间每天 00:00 和 12:00。"
}

start_service() {
    local web_started_here=0

    if web_running && worker_running; then
        echo "后端已经在运行。"
        echo "网页 PID: $(cat "${FLASK_PID_FILE}")"
        echo "自动抓取 PID: $(cat "${WORKER_PID_FILE}")"
        web_urls
        return 0
    fi

    # 首次启动时确保数据库和表结构已经存在。
    "${PYTHON_BIN}" -c "from database import initialize_database; initialize_database()"

    check_proxy_health

    # 旧版本可能通过 python app.py 手工启动，因此没有 PID 文件。
    # 先清理本项目自己的遗留网页进程，再检查端口是否被其他程序占用。
    if ! web_running && port_in_use; then
        stop_untracked_project_web
    fi

    if ! web_running && port_in_use; then
        echo "端口 ${PORT} 已被其他程序占用，无法启动网页。" >&2
        if command -v ss >/dev/null 2>&1; then
            ss -ltnp "sport = :${PORT}" >&2 || true
        fi
        echo "请停止占用该端口的程序，或使用其他端口启动，例如：" >&2
        echo "  FLASK_PORT=5001 ./manage.sh start" >&2
        return 1
    fi

    if ! web_running; then
        start_web
        web_started_here=1
    else
        echo "网页进程已运行，PID: $(cat "${FLASK_PID_FILE}")"
    fi

    if ! worker_running; then
        if ! start_worker; then
            # 如果本次已经启动了网页，但自动抓取进程无法启动，就回滚网页，
            # 避免出现“看似已启动但不会更新数据”的假运行状态。
            if [[ "${web_started_here}" -eq 1 ]]; then
                stop_one_process "网页" "${FLASK_PID_FILE}" "${PROJECT_DIR}/app.py"
            fi
            return 1
        fi
    else
        echo "自动抓取进程已运行，PID: $(cat "${WORKER_PID_FILE}")"
    fi

    echo "后端启动完成：网页可随时刷新，后台会自动更新资讯。"
    echo "查看运行状态：./manage.sh status"
}

stop_one_process() {
    local display_name="$1"
    local pid_file="$2"
    local expected_script="$3"
    local expected_file="${4:-}"

    if ! is_running "${pid_file}" "${expected_script}"; then
        rm -f "${pid_file}"
        echo "${display_name}当前没有运行。"
        return 0
    fi

    local pid
    pid="$(cat "${pid_file}")"
    kill "${pid}"

    # 最多等待 10 秒；若仍未退出，再强制结束，保证 stop 命令不会卡住。
    local attempt
    for attempt in {1..20}; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            rm -f "${pid_file}"
            echo "${display_name}已停止。"
            return 0
        fi
        sleep 0.5
    done

    echo "${display_name}未在 10 秒内退出，正在强制停止。" >&2
    kill -KILL "${pid}" 2>/dev/null || true
    rm -f "${pid_file}"
    echo "${display_name}已停止。"
}

stop_service() {
    # 先停止工作进程，确保不再产生新的数据库写入，再停止网页。
    stop_one_process "自动抓取进程" "${WORKER_PID_FILE}" "${PROJECT_DIR}/auto_fetcher.py"
    stop_one_process "网页进程" "${FLASK_PID_FILE}" "${PROJECT_DIR}/app.py"
}

show_status() {
    local all_running=0

    if web_running; then
        echo "网页进程：运行中（PID $(cat "${FLASK_PID_FILE}")）"
        web_urls
    else
        echo "网页进程：未运行"
        if port_in_use; then
            echo "端口提示：${PORT} 当前仍被其他进程占用。"
            echo "再次执行 ./manage.sh start 会自动尝试清理本项目遗留的旧 app.py。"
        fi
        all_running=1
    fi

    if worker_running; then
        echo "自动抓取进程：运行中（PID $(cat "${WORKER_PID_FILE}")）"
    else
        echo "自动抓取进程：未运行"
        all_running=1
    fi

    return "${all_running}"
}

fetch_news() {
    echo "开始手动抓取，详情会写入 ${FETCH_LOG}"
    "${PYTHON_BIN}" "${PROJECT_DIR}/fetch_news.py" 2>&1 | tee -a "${FETCH_LOG}"
}

show_logs() {
    local log_type="${1:-worker}"
    local line_count="${2:-80}"
    local selected_log

    case "${log_type}" in
        flask)
            selected_log="${FLASK_LOG}"
            ;;
        worker)
            selected_log="${WORKER_LOG}"
            ;;
        fetch)
            selected_log="${FETCH_LOG}"
            ;;
        translation)
            selected_log="${TRANSLATION_LOG}"
            ;;
        *)
            echo "日志类型只能是 flask、worker、fetch 或 translation。" >&2
            return 1
            ;;
    esac

    if [[ ! "${line_count}" =~ ^[1-9][0-9]*$ ]]; then
        echo "日志行数必须是正整数。" >&2
        return 1
    fi

    if [[ ! -f "${selected_log}" ]]; then
        echo "日志文件还不存在：${selected_log}"
        return 1
    fi

    tail -n "${line_count}" "${selected_log}"
}

doctor() {
    # 一次性输出主机访问和 RSS 出站排障所需的关键信息。
    echo "=== Python 与依赖 ==="
    "${PYTHON_BIN}" --version
    "${PYTHON_BIN}" -c \
        "import requests, feedparser, bs4, flask; print('Python 依赖：正常')"

    echo
    echo "=== 虚拟机地址与网关 ==="
    echo "虚拟机 IPv4：$(primary_ip)"
    if command -v ip >/dev/null 2>&1; then
        ip -brief address 2>/dev/null || true
        echo "默认路由："
        ip route show default 2>/dev/null || true
    fi

    echo
    echo "=== 出站网络 ==="
    local gateway
    gateway="$(
        ip route show default 2>/dev/null \
            | awk '/default/ {print $3; exit}' \
            || true
    )"
    if [[ -n "${gateway}" ]] && command -v ping >/dev/null 2>&1; then
        if ping -c 1 -W 2 "${gateway}" >/dev/null 2>&1; then
            echo "VMware 网关 ${gateway}：可连接"
        else
            echo "VMware 网关 ${gateway}：不可连接"
        fi
    fi

    if command -v curl >/dev/null 2>&1; then
        echo "直连互联网测试："
        if curl \
            --noproxy '*' \
            --connect-timeout 5 \
            --max-time 8 \
            -sS \
            -o /dev/null \
            -w 'HTTP %{http_code}\n' \
            https://www.baidu.com; then
            echo "直连互联网：正常"
        else
            echo "直连互联网：失败"
        fi
    fi

    echo
    echo "=== Flask 端口 ==="
    echo "配置监听：${HOST}:${PORT}"
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "sport = :${PORT}" 2>/dev/null || true
    fi
    web_urls

    echo
    echo "=== 代理检测 ==="
    check_proxy_health

    echo
    echo "=== 数据库 ==="
    "${PYTHON_BIN}" - <<'PY'
from database import get_latest_fetch_run, get_news_count, initialize_database

initialize_database()
print(f"已收录新闻：{get_news_count()} 条")
print(f"最近抓取：{get_latest_fetch_run()}")
PY
}

case "${1:-}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        stop_service
        start_service
        ;;
    status)
        show_status
        ;;
    fetch)
        fetch_news
        ;;
    logs)
        show_logs "${2:-worker}" "${3:-80}"
        ;;
    review)
        "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/review_filter.py" --limit 20
        ;;
    backfill)
        "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/backfill_history.py" \
            --days "${2:-60}" 2>&1 | tee -a "${PROJECT_DIR}/data/backfill.log"
        ;;
    translate)
        "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/translate_missing.py" \
            2>&1 | tee -a "${TRANSLATION_LOG}"
        ;;
    doctor)
        doctor
        ;;
    *)
        echo "用法：$0 {start|stop|restart|status|fetch|logs|review|backfill|translate|doctor}" >&2
        echo "日志用法：$0 logs [flask|worker|fetch|translation] [行数]" >&2
        exit 1
        ;;
esac
