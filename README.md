# AI + 音乐每日情报收集系统

本项目是一个运行在 Ubuntu 上的本地 Web 应用。它每天从多个 RSS 源抓取资讯，
筛选 AI、音乐/乐器以及与两者方向相关的硬件内容，保存到 SQLite，并用 Flask
以卡片形式展示。

当前运行模式为“后端常驻自动同步”：

1. 执行 `./manage.sh start` 后同时启动 Flask 网页和后台自动抓取进程。
2. 自动抓取进程在北京时间每天 00:00 和 12:00 刷新全部来源。
3. 新资讯经过去重后写入 SQLite；网页只读取数据库。
4. 你日常打开网页或刷新页面即可看到最新内容，不需要手动点击抓取。
5. 执行 `./manage.sh stop` 后，网页和自动抓取进程同时停止。

RSS 不是真正的实时推送协议，所以这里采用固定时间轮询。

## 一、原始项目需求

### 项目背景与当前环境

1. 操作系统：Ubuntu 24.04（VMware 虚拟机）。
2. Python 3.14，已安装 `requests`、`feedparser`、`beautifulsoup4` 和 `flask`。
3. 已安装 Microsoft Edge、Git、Node.js，本机网络已配置代理加速。
4. 项目最初计划位于 `~/Desktop/python/Python/`。

### 核心需求

- 使用 `feedparser` 循环抓取多个 RSS 源，并正确处理代理与网络请求。
- 初始计划使用公共 RSSHub，但该实例在当前虚拟机网络下连接超时，因此已切换为
  当前网络可直接访问的官方 RSS 和 Bing News RSS：
  - IT之家：`https://www.ithome.com/rss/`
  - 爱范儿：`https://www.ifanr.com/feed`
  - 36氪、少数派、钛媒体、极客公园、雷锋网：国内科技 RSS
  - TechCrunch：`https://techcrunch.com/feed/`
  - Bing 中文新闻搜索：AI 音乐硬件、智能乐器、音频硬件、合成器，用于
    补充没有稳定公开 RSS 的国内行业网站和中文媒体
  - Music Business Worldwide、MusicRadar、Guitar World、Synthtopia、CDM、
    MusicTech、Rekkerd、Synthanatomy、Attack Magazine、ProSoundNetwork、
    MIX、Matrixsynth：面向音乐产业、乐器、音频制作和音乐科技的垂直媒体
  - 公共 RSSHub 实例和机器之心 Feed 经实测存在超时或 XML 格式错误，已移除，
    避免每轮产生无效请求
- 资讯只要包含 AI、音乐或乐器关键词之一就会保留；同时命中 AI 与音乐
  的内容会获得额外相关度加权并优先排名。
  - AI 关键词：`ai`、`人工智能`、`大模型`、`aigc`、`机器学习`，
    以及 `artificial intelligence`、`machine learning` 等英文同义词
  - 音乐关键词：`音乐`、`吉他`、`编曲`、`歌手`、`乐器`、`音色`，
    以及 `music`、`guitar`、`song` 等英文同义词；泛化的“音频”单独出现
    不再算音乐资讯，只有“音频生成”“AI 音频”等组合词才计入
  - 匹配不区分大小写。
- 使用本地 SQLite 数据库，`news` 表包含：
  `id`、`title`、`link`、`source`、`publish_time`、`summary`、`category`。
- 以 `link` 作为唯一标识去重。
- Flask 首页按发布时间倒序展示标题、简介、来源和发布时间，并显示抓取时间与总条数。
- 抓取入口可以独立调用，以便之后用 Linux cron 定时运行。
- 增加搜狗微信公开搜索适配器；不绕过验证码、登录或平台访问限制。

## 二、当前实现结构

```text
Ai-Collect/
├── app.py                 # Flask 只读网页和筛选分页
├── auto_fetcher.py        # 常驻后台抓取进程和定时轮询
├── fetch_news.py          # cron/命令行抓取入口
├── config.py              # RSS 源、关键词、代理和路径配置
├── custom_sources.json    # 用户授权的公众号 RSS、其他自定义 RSS
├── database.py            # SQLite 建表、去重写入和查询
├── news_filter.py         # AI + 音乐双重关键词过滤
├── ranking.py             # 时间筛选、关键词搜索和综合排行
├── rss_fetcher.py         # RSS 下载、解析、清洗与入库
├── sogou_wechat.py        # 搜狗微信公开结果页解析
├── manage.sh              # 一键启动、停止、重启、查看状态
├── templates/index.html   # 首页模板
├── static/style.css       # 卡片式页面样式
├── tests/test_core.py     # 过滤、存储、心跳和网页测试
├── tests/test_rss_fetcher.py # 使用模拟 RSS 的离线解析测试
├── tests/test_auto_fetcher.py # 后台抓取循环测试
├── requirements.txt
└── data/                  # 运行时生成数据库、PID 和日志
```

数据库默认位于 `data/news.db`。新闻存放在 `news` 表中，每次抓取的成功源数量、
命中数量、新增数量和错误信息存放在 `fetch_runs` 表中。后台工作进程还会定期
写入心跳，网页据此显示自动同步是否在线。时间是 UTC 入库，页面默认转换为
`Asia/Shanghai` 时区显示。

Flask 和自动抓取分别运行在两个进程中：

```text
manage.sh
├── app.py            读取 SQLite，提供网页；不负责定时抓取
└── auto_fetcher.py   定时下载 RSS，过滤并写入 SQLite
```

两个进程共享一个 Linux 文件锁，避免多个后台任务同时抓取。

## 三、第一次运行

进入项目目录并直接启动后端：

```bash
cd ~/Desktop/Ai-Collect
./manage.sh start
```

启动脚本后，后台会按北京时间每天 00:00 和 12:00 自动更新。在浏览器打开：

```text
http://127.0.0.1:5000/
```

页面右上角会显示“后台自动同步中”，以及最近一次抓取时间。之后只需要刷新
浏览器，新数据会从 SQLite 自动读取出来。

如果依赖意外缺失，可先执行：

```bash
python3 -m pip install -r requirements.txt
```

## 四、快速启动与结束

```bash
# 启动
./manage.sh start

# 查看状态
./manage.sh status

# 停止
./manage.sh stop

# 重启
./manage.sh restart

# 不打开网页，直接抓取一次
./manage.sh fetch

# 查看最近 80 行网页、后台自动抓取或命令行抓取日志
./manage.sh logs flask
./manage.sh logs worker
./manage.sh logs fetch 200

# 显示虚拟机 IP、默认网关、端口、代理和数据库状态
./manage.sh doctor
```

脚本使用 `data/flask.pid` 和 `data/worker.pid` 记录两个进程编号。
网页日志写入 `data/flask.log`，自动抓取日志写入 `data/worker.log`，
命令行抓取日志写入 `data/fetch.log`。关闭终端不会停止服务，必须执行
`./manage.sh stop`。

如果提示脚本没有执行权限，先运行一次：

```bash
chmod +x manage.sh
```

## 五、从 Windows 主机访问虚拟机网页

Flask 默认监听 `0.0.0.0:5000`，因此虚拟机内部和 Windows 主机都可以访问。
`0.0.0.0` 是监听所有网卡的配置，不是浏览器应该输入的网站地址。

先执行：

```bash
./manage.sh doctor
```

找到“虚拟机 IPv4”，然后在 Windows 主机浏览器访问：

```text
http://虚拟机IPv4:5000/
```

如果仍无法访问：

1. 在 VMware“虚拟机设置 → 网络适配器”中确认已连接。
2. 推荐使用 NAT 模式；只有需要让其他物理设备访问时才考虑桥接模式。
3. 检查 Ubuntu 防火墙：

```bash
sudo ufw status
sudo ufw allow 5000/tcp
```

`5000` 只是 Flask 的默认端口，可以改成其他空闲端口：

```bash
FLASK_PORT=8080 ./manage.sh restart
```

## 六、恢复虚拟机外网

网页能从主机打开，只代表“入站访问正常”；RSS 抓取还要求虚拟机能主动访问
外网。先检查默认路由和基础网络：

```bash
ip -brief address
ip route show default
curl -I --max-time 10 https://www.baidu.com
```

如果没有默认路由，或提示 `Network is unreachable`：

1. 检查 VMware 虚拟机网络适配器是否已连接。
2. 使用 NAT 模式，并确保 Windows 的 VMware NAT 服务正在运行。
3. 在 Ubuntu 中重新启用 NetworkManager：

```bash
sudo nmcli networking on
sudo systemctl restart NetworkManager
```

如果代理软件运行在 Windows 主机上，虚拟机中的 `127.0.0.1` 指向虚拟机自己，
不能访问 Windows 的 `127.0.0.1:7890`。此时必须：

1. 在代理软件中开启“允许局域网连接”。
2. 使用 VMware 网关或 Windows 主机局域网 IP，而不是 `127.0.0.1`。
3. 在虚拟机中测试：

```bash
curl -I --max-time 10 --proxy http://网关IP:7890 \
  https://rsshub.app/36kr/newsflashes
```

测试成功后配置并重启：

```bash
export NEWS_PROXY="http://网关IP:7890"
./manage.sh restart
```

## 七、代理设置

`requests` 会自动读取终端的 `HTTP_PROXY` 和 `HTTPS_PROXY`。cron 环境通常
不继承这些变量，因此可以统一设置 `NEWS_PROXY`：

```bash
export NEWS_PROXY="http://127.0.0.1:7890"
./manage.sh restart
```

请把端口替换成你本机实际使用的代理端口。设置代理后需要重启后端，让后台
自动抓取进程继承新环境变量。不要在代码里写死代理地址。

自动刷新时间是固定的北京时间每天 `00:00` 和 `12:00`，不需要修改环境变量。

### 常见启动问题

如果看到 `Address already in use` 或 `Port 5000 is in use`，通常是有旧版
`app.py` 或另一个软件占用了端口。先查看占用者：

```bash
ss -ltnp 'sport = :5000'
```

新版 `manage.sh start` 会自动识别并重启“工作目录为本项目”的旧 `app.py`；
如果是其他程序占用，不会误杀，只会提示你更换端口：

```bash
FLASK_PORT=5001 ./manage.sh start
```

如果日志中出现：

```text
HTTPSConnection(host='127.0.0.1', port=7890): Connection refused
```

表示代理软件没有启动，或者代理端口不是 `7890`。请先启动代理，或清除旧代理
环境变量后再重启：

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
./manage.sh restart
```

新版抓取器遇到代理连接失败时，会自动创建一个不使用环境代理的会话来尝试
直连，因此代理软件临时未启动不会立即让系统完全失效。如果当前网络必须使用
代理，不希望程序直连，可以关闭兜底：

```bash
export NEWS_DIRECT_FALLBACK=0
./manage.sh restart
```

## 八、测试是否成功

### 1. 自动化测试

```bash
cd ~/Desktop/Ai-Collect
python3 -m unittest discover -s tests -v
```

预期看到 `OK`。目前共有 82 项测试，会检查过滤、大小写、词边界、模拟 RSS、
搜狗微信解析、分类字段、链接去重、抓取状态、工作进程
心跳、跨进程抓取锁、时间范围筛选、关键词搜索、综合排名、首页渲染和非法
查询参数，以及 GitHub 新项目与 commit 解析，不依赖当前网络状态。

### 2. 首页筛选与排行

首页默认显示最近 3 天的资讯，也可以选择最近 1、7、14、30、60 天，
或者指定某一个具体日期。时间范围、日期和搜索条件改变后会自动刷新，不需要
再次点击“筛选”。列表每页固定显示 20 条，底部通过上一页、下一页和页码切换。

资讯筛选栏恢复使用“全部、硬件相关、软件相关”下拉框，并与时间范围、指定
日期、关键词和分页共同生效。数据库为每条资讯保存 `is_hardware` 和
`is_software` 两个标记；同时涉及实体设备与配套软件的资讯允许两个标记都为真，
因此会同时出现在硬件和软件筛选结果中。旧数据库首次启动时会自动补分类，以后
新抓取的资讯在写入数据库时自动分类。

关键词搜索覆盖中文标题、英文原标题和简介，例如“吉他”“钢琴”“乐理”。
多个关键词必须使用中文或英文分号分隔，例如 `MIDI；吉他；编曲`；没有分号时，
整个输入会作为一个完整短语搜索，空格不会自动拆分。

“最近 N 天”按北京时间自然日计算，而不是滚动 N×24 小时。例如 11 月 18 日
选择最近 3 天，只包含 11 月 18、17、16 日，不包含 15 日。

指定日期使用文章的真实发布时间匹配；没有发布时间的文章不会冒充某一天的数据。
如果某一天本地数据库没有内容，后端会按该日期的搜狗范围补抓一次。

数据库只保留北京时间今天及之前 59 个自然日的数据。每次抓取和回填后会删除
超过 60 天的内容，以及无法确认发布时间的内容，避免 2023 年旧报告混入信息库。

首次使用建议回填最近 60 天：

```bash
./manage.sh backfill 60
```

回填过程会逐来源、逐页输出进度。标题翻译与历史下载分开处理，避免上千条
英文标题逐条调用翻译接口时让命令看起来卡死；需要补齐翻译时单独运行
`./manage.sh translate`。

回填会依次尝试 Synthtopia、MusicTech、Synthanatomy、Rekkerd、Attack
Magazine、ProSoundNetwork、MIX、Music Business Worldwide、爱范儿和
TechCrunch 的 WordPress 归档 API，读取接口提供的 `date_gmt` 并以 UTC
入库。没有可靠发布时间的文章不会进入历史排行，也不会用抓取当天的时间冒充
历史发布时间。

当前额外数据源：

- Rekkerd、Synthanatomy、Attack Magazine、ProSoundNetwork、MIX、
  Matrixsynth 的 RSS
- arXiv `cs.SD` 声音与音乐计算 RSS
- AudioCraft、Stable Audio Tools、Magenta、Riffusion、Demucs、Sonic Pi
  的 GitHub Releases
- GitHub 新项目与 commit 自动发现：搜索近 14 天新建的 AI 音乐仓库，以及
  近 3 天与 AI 音乐、音乐生成、音频生成有关的 commit

Gearnews 当前返回 429 限流，KVR Audio 返回 403，虎嗅持续超时，品玩 RSS
格式损坏，因此这些来源已停用，避免每轮抓取产生无意义请求。

GitHub 自动发现不要求你提前填写仓库名。程序会查询 `ai music`、
`music generation`、`music production`、`MIDI` 和 `ai-music`
主题下的新仓库，并搜索包含音乐生成、音频生成、MIDI、混音等方向的近期
commit；
每条结果都保存项目简介、真实时间和 GitHub 链接。新项目标题统一为
`GitHub - 新发布：简介`，Release 和 commit 标题统一为
`GitHub - 新更新：简介`，可直接搜索 `Git` 或 `GitHub` 找到。README、依赖
升级、格式化和 CI 等低信息量 commit 会被跳过，重叠结果按链接去重。该模块
默认启用，可通过环境变量 `GITHUB_DISCOVERY_ENABLED=0` 临时关闭。批量账号
投递的代理、直播引流、账号多开等垃圾 commit 会在入库前被剔除。

抓取主流程与英文标题翻译相互独立。抓取完成后先记录成功状态并释放锁，
翻译由另一个后台进程每次最多处理 80 条，避免翻译接口限速导致抓取看起来
卡死。翻译进度可通过 `./manage.sh logs translation` 查看。

指定日期没有数据时，后端会查询这些历史归档接口一次。日期范围筛选始终按
真实发布时间计算，不使用“抓取时间”代替“发布时间”。

编辑过滤采用“AI、音乐或方向硬件”并集：AI 硬件、NPU/推理芯片、端侧 AI、
智能硬件、智能音箱和可穿戴设备，以及 MIDI 控制器、合成器、鼓机、采样器、
效果器、音频接口、声卡、麦克风、监听设备和电子乐器均可收录。AI + 音乐、
AI + 硬件、音乐 + 硬件会获得额外排序权重。

普通手机、机械键盘和家电只有同时出现明确的 AI、音乐、乐器或音频方向词时
才会收录，避免单纯按“硬件”二字把所有消费电子产品都抓进来。高管变动、
诉讼、融资、明星八卦、巡演、榜单、购物优惠和纯观点内容仍会被排除。

对于已审核的国内科技、国际科技、音乐科技和搜狗微信来源，不再要求每篇文章
重复命中关键词；只要标题不触发噪音规则即可收录。相关度和热度仍用于内部
排序，但不在资讯列表中显示。

列表首先严格按真实发布时间倒序排列；只有发布时间相同时，才使用综合分决定
先后。综合分公式仅用于后台排序：

```text
综合分 = 相关度 × 50% + 热度 × 30% + 新鲜度 × 20%
```

相关度由 AI/音乐关键词覆盖和标题命中位置计算；新鲜度按 72 小时线性衰减；
公开 RSS 不提供真实阅读量，因此热度由来源权重、类别和新闻热词估算。

### 3. 抓取测试

```bash
python3 fetch_news.py
```

成功时终端会显示成功源数量、RSS 条目数、关键词命中数和新增条数。
如果所有来源都失败，命令会返回非零退出码并打印错误原因。

### 4. 数据库检查

```bash
python3 - <<'PY'
import sqlite3

connection = sqlite3.connect("data/news.db")
print("资讯总数：", connection.execute("SELECT COUNT(*) FROM news").fetchone()[0])
for row in connection.execute(
    "SELECT source, title, publish_time FROM news ORDER BY publish_time DESC LIMIT 5"
):
    print(row)
PY
```

### 5. 网页检查

```bash
./manage.sh start
curl http://127.0.0.1:5000/health
```

预期返回类似：

```json
{"database":"0 articles","status":"ok"}
```

然后打开 `http://127.0.0.1:5000/` 查看页面。若页面正常但仍无卡片，
先查看 `data/flask.log`，再确认当前 RSS 中是否存在同时命中两类关键词的内容。

## 九、搜狗微信来源

搜狗微信搜索关键词位于 `config.py` 的 `SOGOU_WECHAT_QUERIES`。程序使用
普通公开结果页，不会绕过验证码、登录或风控；平台限制该来源时，只在日志中
记录失败，不影响稳定 RSS 来源。

搜狗来源默认每 12 小时刷新一次，使用二十四个领域词发现公众号内容，
每个词读取前两页，查询之间间隔 2 秒。如果第一个关键词
遇到访问限制，本轮会停止剩余关键词，避免连续请求扩大限制。搜狗跳转链接包含
临时 token，因此数据库使用“规范化标题指纹”去重，而不直接依赖链接去重。

公众号发现词包括 `AI`、`人工智能`、`AIGC`、`AI音乐`、`AI音频`、
`音乐`、`吉他`、`乐器`、`音频`、`编曲`、`乐理`、`音乐制作`、`MIDI`、
`混音`、`母带`、`音频插件`、`DAW`、`音源`、`音乐生成`，并保留
`Suno`、`Suno AI MV`、`AI MV` 和 `音乐视频` 等品牌/事件词。
这些宽泛词负责发现内容，抓取后再由分类器判断硬件或软件，不在搜索阶段
用具体产品名限制范围。搜狗只能检索其公开索引中的公众号文章，无法读取你
手机微信关注列表；如果官方账号文章尚未进入搜狗索引，仍需通过授权 RSS
桥接或手动提供文章链接才能保证收录。

没有解析到真实发布时间的文章不会入库，避免旧文章被误认为近期内容。

如果你在 WeRSS 等合规服务扫码授权了公众号，并得到专属 RSS 地址，可以编辑
`custom_sources.json`：

```json
{
  "sources": [
    {
      "source": "我的公众号",
      "url": "https://example.com/wechat/feed.xml",
      "category": "微信公众号"
    }
  ]
}
```

保存后执行 `./manage.sh restart` 即可。该文件只保存 RSS 地址，不保存微信账号、
密码或 Cookie。

## 十、GitHub Pages（免费长期在线）

GitHub Pages 是无服务器方案，适合不希望购买云服务器的场景。它不是直接运行
Flask，而是由 GitHub Actions 每 12 小时执行 Python 抓取，把结果写入
`public/data/news.json`，再由 GitHub Pages 发布静态网页。

已包含：

- `.github/workflows/update-pages.yml`：定时抓取、提交数据、部署 Pages
- `public/index.html`、`public/app.js`：静态搜索、天数筛选与排行
- `translation.py`：英文标题自动翻译和持久缓存
- `scripts/github_update.py`：恢复历史数据、抓取和导出 JSON

GitHub Actions 会自动把临时 `GITHUB_TOKEN` 传给抓取程序，以提高 API 限流
额度；这个令牌由 GitHub 临时生成，不会写入网页或仓库文件。不需要你再创建
额外令牌。主动推送代码或手动运行工作流时，Actions 会先执行一次最近 60 天
历史回填再导出网页；每 12 小时的定时任务只抓取当期资讯。

### 1. 推送代码

先从 GitHub 克隆现有仓库，再把本地完整项目覆盖进去。这样不会破坏远程已有
历史，也不会出现 unrelated histories：

```bash
cd ~/Desktop
git clone https://github.com/Andy-Dufrense/Ai-Collect.git Ai-Collect-GitHub
cp -a Ai-Collect/. Ai-Collect-GitHub/
cd Ai-Collect-GitHub
git add .
git commit -m "feat: AI music intelligence site"
git push -u origin main
```

GitHub 不再接受账号密码推送，浏览器会要求登录或 Personal Access Token。

### 2. 开启 Pages

在 GitHub 仓库中打开：

```text
Settings → Pages → Build and deployment → Source
```

选择 `GitHub Actions`。

### 3. 运行第一次抓取

打开：

```text
https://github.com/Andy-Dufrense/Ai-Collect/actions/workflows/update-pages.yml
```

点击 `Run workflow`。成功后访问：

```text
https://Andy-Dufrense.github.io/Ai-Collect/
```

之后 Actions 会在 UTC 04:00 和 16:00（北京时间 12:00 和次日 00:00）
自动运行。

英文标题会通过 MyMemory 免费翻译接口转换为简体中文，并缓存到
`news.json`。同一标题不会重复翻译；接口限流时保留英文原文，不影响站点更新。
搜索会同时匹配英文原标题和中文翻译。

普通抓取、60 天回填和指定日期补抓都会在文章入库后自动翻译标题。历史积压
可通过下面命令补齐：

```bash
./manage.sh translate
```

注意：GitHub Actions 的定时任务可能有几分钟延迟；仓库需为 Public 才能免费
使用 GitHub Pages（具体以 GitHub 当前规则为准）。搜狗微信可能限制云数据中心
IP，但 RSS 和授权公众号 RSS 不受影响。

## 十一、部署到云服务器（可选）

如果希望关闭 Windows 和 VMware 虚拟机后，网页仍然随时可以访问，推荐部署
到一台 Ubuntu 24.04 云服务器。项目已经包含一键部署文件：

```text
deploy/install.sh
deploy/ai-music-web.service
deploy/ai-music-worker.service
deploy/nginx-ai-music.conf
wsgi.py
```

### 1. 准备服务器

1. 购买一台 Ubuntu 24.04 云服务器，1 核 1GB 内存即可。
2. 在云平台安全组中放行 TCP `22`（SSH）和 TCP `80`（网页）。
3. 记录服务器的公网 IP 和 SSH 登录方式。

### 2. 上传项目

在 Windows PowerShell 中进入项目上级目录，把整个项目上传：

```powershell
scp -r .\Ai-Collect root@服务器公网IP:/root/
```

把“服务器公网IP”替换成实际地址。如果登录用户不是 `root`，同时替换 `root@`。

### 3. SSH 登录服务器

```bash
ssh root@服务器公网IP
```

### 4. 执行一键安装

```bash
cd /root/Ai-Collect
sudo bash deploy/install.sh
```

安装脚本会自动完成：

- 安装 Python、Gunicorn、Nginx
- 创建独立系统用户 `ai-music`
- 安装到 `/opt/ai-music`
- 创建 Python 虚拟环境
- 启动 Web 和自动抓取服务
- 设置开机自启和崩溃自动重启
- 配置 Nginx 反向代理

### 5. 访问

```text
http://服务器公网IP/
```

首页、搜索和筛选公开只读访问。服务器重启后服务会自动恢复，不需要再执行
任何启动命令。

### 6. 查看运行状态

```bash
systemctl status ai-music-web
systemctl status ai-music-worker
journalctl -u ai-music-worker -f
```

### 7. 更新代码

重新上传项目并再次执行安装脚本即可。脚本会保留服务器上的数据库、
日志和 `custom_sources.json`：

```bash
cd /root/Ai-Collect
sudo bash deploy/install.sh
```

如果需要域名和 HTTPS，下一步可以为服务器公网 IP 绑定域名，并使用 Certbot
申请免费 TLS 证书。

## 十二、cron 定时抓取（可选替代方案）

正常使用时不需要 cron：只要执行 `./manage.sh start`，后台工作进程就会持续
抓取；执行 `./manage.sh stop` 后同步停止。

如果你以后不希望保持后端常驻，才可以用 cron 替代自动工作进程。不要同时
启用常驻工作进程和同一间隔的 cron，否则只是重复触发，虽然文件锁和数据库
去重能保证不重复入库，但会产生不必要的网络请求。

先确认 Python 绝对路径：

```bash
command -v python3
```

用 `crontab -e` 编辑定时任务。下面的示例表示北京时间每天 00:00 和 12:00
抓取：

```cron
0 0,12 * * * cd /home/andy/Desktop/Ai-Collect && /usr/bin/python3 fetch_news.py >> /home/andy/Desktop/Ai-Collect/data/cron.log 2>&1
```

如果不需要代理，删除 `NEWS_PROXY=...` 部分。网页服务与抓取任务分离，
使用 cron 时不需要为抓取保持 Flask 常驻运行。

## 十三、后续扩展

- 增加 RSS 源：编辑 `config.py` 中的 `RSS_SOURCES`。
- 修改关键词：编辑 `config.py` 中的 `AI_KEYWORDS` 和 `MUSIC_KEYWORDS`。
- 修改数据库位置：设置环境变量 `NEWS_DB_PATH`。
- 修改端口：启动前设置环境变量 `FLASK_PORT`，例如 `FLASK_PORT=8000 ./manage.sh start`。
