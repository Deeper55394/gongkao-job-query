# 公考职位查询工具 · 本科 · 生物科学（师范） · 江苏

一个 **纯前端 + 自动更新** 的公考职位筛选工具：筛选【国家公务员考试（国考）】与【江苏省公务员考试（省考）】中，适合
**本科、生物科学（师范）专业、江苏地区** 报考的岗位，并明确标出「需电话咨询招录单位」的风险点。

- 前端：单文件 `index.html`，**双击即可打开**，无需服务器、无后端、数据不外传，手机端可用。
- 数据：`scraper.py` 从**官方渠道**抓取职位表 Excel，用 pandas 清洗后生成 `data.json`。
- 自动化：`.github/workflows/update.yml` 每天 UTC 02:00（北京时间 10:00）自动抓取、提交、部署。
- 托管：GitHub Pages 免费在线访问。

> ✅ **当前数据**：`data.json` 里已是**真实职位数据** —— 江苏省2026年度考试录用公务员官方职位表
> （省人社厅「岗位信息」栏目原件：省级机关 + 13 个设区市 + 垂管单位，共 6157 个职位；
> 按「江苏 + 生物科学（师范）相关」收窄、并排除定向招录岗位后，收录 **497 条**）。
>
> **年度策略**：默认只保留每类考试的**最新年度**（`--year-policy latest`）——
> 官方一发布新年度职位表并被抓到，旧年度记录会被**自动替换**（想留历年用 `--year-policy keep-all`）。
>
> ⚠️ 本工具不生成、不推断、不编造任何职位数据：所有字段逐字取自官方职位表原件；
> 抓不到数据时保留旧数据、写明原因。报名条件一律以官方公告、职位表原件及招录单位答复为准。

> 📖 **第一次用请先看：[使用教程.html](使用教程.html)**（双击即可阅读，带目录，可打印成 PDF）或 [先看这里.txt](先看这里.txt)。
> Markdown 源文件是同目录的 `使用教程.md`，改完执行 `python tools/md2html.py 使用教程.md` 重新生成 HTML。
>
> 🚀 **要部署到网上：[部署到GitHub Pages.html](部署到GitHub%20Pages.html)**（不用装任何软件也能部署，含网页拖拽上传的完整步骤）。

---

## 一、目录结构

```
gongkao-job-query/
├── index.html                        # 【前端】单文件页面：筛选 / 展示 / 导出 CSV（内嵌最新数据，双击即用）
├── 创建桌面快捷方式.bat                 # 【Windows】一键在桌面生成「公考职位查询」快捷方式（带自定义图标）
├── 部署到GitHub.bat                   # 【Windows】一键把项目推送到你的 GitHub 仓库（需先装 Git）
├── 检查新职位表.bat                    # 【Windows】检查官方是否已发布新年度职位表（可自动更新）
├── 安装提醒.bat                        # 【Windows】开启「每天自动检查 + 发现新表弹窗提醒」计划任务
├── 取消提醒.bat                        # 【Windows】关闭上面的计划任务
├── jiangsu_regions.json               # 江苏 区县->设区市 映射（城市筛选与咨询电话归属共用）
├── 启动.bat                           # 【Windows】一键启动本地服务并打开页面（可自动读取 data.json）
├── 更新数据.bat                       # 【Windows】把官方职位表拖上去 → 自动生成 data.json 并同步进 index.html
├── start.sh                           # 【macOS/Linux】bash start.sh 一键启动
├── icon.ico                           # 快捷方式图标（由 tools/make_icon.py 生成）
├── xlsx.full.min.js                   # 页面内离线解析 Excel 用的 SheetJS（本地优先，加载不到才走 CDN）
├── 使用教程.md / 使用教程.html          # 【教程】面向使用者的完整图文教程（Markdown 源 + 可双击阅读的 HTML）
├── 部署到GitHub Pages.md / .html       # 【教程】部署到 GitHub Pages 的完整步骤（含"不用装软件"的网页上传法）
├── 先看这里.txt                        # 【教程】给非技术用户的上手说明
├── scraper.py                         # 【数据】抓取 + 解析 + 清洗 + 生成 data.json
├── data.json                          # 【数据】真实职位数据（江苏省2026年度官方职位表，497 条相关职位）
├── requirements.txt                   # Python 依赖
├── README.md                          # 本文件
├── .nojekyll                          # GitHub Pages 需要（跳过 Jekyll 处理）
├── .gitattributes                     # 统一换行符（保证 .bat 在 Windows 上是 CRLF）
├── .github/
│   └── workflows/
│       └── update.yml                 # 【自动化】每天定时抓取 + 提交 + 部署 Pages
├── samples/
│   ├── 示例_江苏省考职位表.xlsx         # 示例职位表（虚构，用于跑通流程/自测）
│   └── 示例_国考职位表.xlsx             # 示例职位表（虚构，用于跑通流程/自测）
├── tools/
│   ├── serve.py                       # 本地静态服务（供 启动.bat / start.sh 调用）
│   ├── update_data.py                 # 拖入 Excel 后的交互式更新引导（供 更新数据.bat 调用）
│   ├── probe_new_cycle.py             # 新年度职位表探针（可按年点名检查/发现即自动更新）
│   ├── make_shortcut.ps1              # 桌面快捷方式的实际创建逻辑（供 创建桌面快捷方式.bat 调用）
│   ├── deploy_github.ps1              # 推送代码到 GitHub 的实际逻辑（供 部署到GitHub.bat 调用）
│   ├── make_icon.py                   # 生成 icon.ico 图标与预览图（Pillow）
│   ├── build_standalone.py            # 把 data.json 内嵌进 index.html（"双击即用"的关键）
│   ├── make_package.py                # 打包分发：ZIP + 独立单文件 HTML + GitHub 部署包
│   ├── make_sample_excel.py           # 生成上面的示例 Excel
│   ├── md2html.py                     # 把 Markdown 教程渲染成单文件 HTML（带目录/可打印）
│   ├── check_html.py                  # HTML 结构自检（标签配对 + 关键元素统计）
│   ├── check_workflow.py              # GitHub Actions 工作流自检（YAML/权限/引用文件）
│   └── smoke_test_frontend.mjs        # （可选）用 Node 对前端逻辑做冒烟测试（含浏览器上传 Excel 的场景）
└── downloads/                         # 运行时自动创建：存放下载到的官方职位表原件
```

> **data.json 与 index.html 的关系**：`data.json` 是唯一数据源；`tools/build_standalone.py` 会把它的内容内嵌进 `index.html`，
> 这样双击 `index.html` 也能直接看到数据。**只要更新了 data.json，就顺手跑一次**
> `python tools/build_standalone.py`（GitHub Actions 已自动做这一步；用 `更新数据.bat` 也会自动做）。

> **维护须知**：`index.html` 里的 `HEADER_ALIASES`（浏览器端表头映射）必须与 `scraper.py` 里的 `COLUMN_ALIASES`
> 保持一致 —— 两处不一致会导致"浏览器上传职位表"和"scraper.py 解析"得到不同字段（曾经出现招录机关整列空白）。
> 改完可用 `node tools/smoke_test_frontend.mjs`（阶段 3 专门测浏览器上传）验证。

### 国考数据现状（已打通自动更新通道）

国考专题站 `bm.scs.gov.cn` 是**纯 JS 应用**（页面 2~4KB、0 个链接），静态爬虫拿不到任何附件。
但它的常量脚本里写着真正的数据接口，工具已据此**打通国考自动通道**：

- `GET http://dl.scs.gov.cn/pp/gkweb/core/web/ui/js/core/core-constant.js`
  → `neu.hb01Id="8a81f6d9…"`（本年度专题 id）、`neu.aae001="2026"`（年度）
- `GET {cdnServer}/api/res/{hb01Id}/1110` → `resList`（官方附件列表）
- `GET {downloadServer}{resResourceId}` → 官方原件（招考简章 / 职位表）

**关键好处：年度专题 id 由官方脚本给出，每年换专题时自动跟着变，不需要改代码** ——
所以国考会和省考一样自动更新。

2026 年度官方共 3 张职位表（招考简章 20714 条、调剂 1632 条、补充录用 927 条），
按「江苏 + 生物科学（师范）相关」收窄后收录 **20 条**（完全匹配 A 类 1 条：中国证监会江苏监管局，专业列「理学类」）。

> ⚠ 现状提示：国考江苏可报岗位很少。2026 年度真正完全匹配的只有 1 条；其余多是
> 「**化学生物学**」「**生物统计学**」这类字面含"生物"、实际属化学/统计的专业，
> 工具判为 **D 类**并提示需电话核实。同一轮江苏省考收录 497 条，才是主战场。

**手动导入（备用）**：从官方下载职位表 Excel，拖进 `更新数据.bat` 并选「国考」；
国考与省考记录**并存互不覆盖**（唯一键与年度策略都按考试类型区分）。

### 新年度职位表提醒（推荐开启）

双击 **`安装提醒.bat`** 即可注册一个 Windows 计划任务（当前用户、无需管理员）：

- 每天 **10:30** 自动跑一次轻量探测（只看几个官方页面）；
- **没发现新表 → 完全静默**，只往 `提醒记录.log` 写一行；
- **发现新表 → 弹窗提醒**，点「是」立刻抓取 → 内嵌 → 推送（约 1-3 分钟）；
- 同一年度只提醒一次（状态存在 `.remind-state.json`），不会天天骚扰你。

管理命令（也可以直接双击对应 bat）：

```
powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action status    # 查看状态/最近记录
powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action test      # 弹一次演示提醒
powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action run       # 立刻按真实逻辑检查一次
powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action install -Time 09:00   # 改时间
```

关闭：双击 `取消提醒.bat`。注意：任务只在**你登录时**运行（否则无法弹窗）。

---

## 二、直接使用（四种方式，按需选一种）

### 方式 0：双击桌面上的「公考职位查询」

先双击项目里的 `创建桌面快捷方式.bat`，桌面就会出现**公考职位查询**快捷方式（自带图标）：

- 已装 Python → 快捷方式启动本地服务并打开浏览器，自动读取最新 `data.json`（黑窗口最小化，用完关掉即可）；
- 没装 Python → 直接用浏览器打开页面（页面自带数据，筛选/导出功能一样全，还可在页面里直接上传 Excel）。

想再要一个"更新数据"的快捷方式：`创建桌面快捷方式.bat both`。
移动了项目文件夹后，重新双击一次 `创建桌面快捷方式.bat` 即可修复快捷方式。

### 方式 1：双击 `index.html`（零配置，最快）

双击即可，页面会**自动载入内置数据**（当前 497 条真实的江苏省考职位），筛选、查看、导出 CSV 全部可用，无需联网、无需 Python。

> 为什么不是直接读 data.json？浏览器在 `file://` 协议下禁止读取本地文件（安全策略）。
> 因此项目把 data.json 内嵌进页面作为兜底，并在顶部提示"已载入页面内置数据"。
> **想让页面用最新数据**，用下面两种方式之一。

> **没有 Python 也想用真实数据？** 打开页面后点「选择职位表（Excel / CSV）」，直接选中官网下载的 `.xlsx` 即可：
> 项目自带 `xlsx.full.min.js`（SheetJS 社区版），**离线就能解析**，解析完立即可以筛选和导出 CSV。

### 方式 2：双击 `启动.bat`（推荐，能自动读取最新 data.json）

双击 `启动.bat` → 自动起本地服务并打开浏览器（默认 http://127.0.0.1:8765/ ），页面会自动读取 `data.json`，
效果与 GitHub Pages 完全一致；**无需安装任何 Python 依赖**（只用标准库）。

```bat
启动.bat                :: 默认 127.0.0.1:8765
启动.bat --port 9000    :: 换端口
启动.bat --lan          :: 手机同 WiFi 访问（会打印手机可用的网址）
```

macOS / Linux 用户：`bash start.sh`（参数相同）。

### 方式 3：更新成真实数据

1. 打开官方公告页，下载职位表 Excel（[国考专题](http://bm.scs.gov.cn/kl2026)、[江苏先锋网](https://www.jszzb.gov.cn/)、[江苏省人社厅](https://jshrss.jiangsu.gov.cn/)）；
2. 把 Excel 文件**用鼠标拖到 `更新数据.bat` 上**，按提示输入考试类型/年度（回车即默认），程序会自动：
   安装依赖（首次）→ 解析清洗 → 生成 `data.json` → 同步进 `index.html`；
3. 完成后双击 `index.html` 或 `启动.bat` 查看。

等价的命令行方式（推荐在 CI/服务器上使用）：

```bash
python scraper.py --local "职位表.xlsx" --exam-type 江苏省考 --year 2026 --source-url "官方公告页网址"
python tools/build_standalone.py        # 同步进 index.html，保证双击也能看到新数据
```

> **想分享给别人 / 换台电脑用**：执行 `python tools/make_package.py`，会在项目上级目录生成两个文件：
> ① `公考职位查询工具_日期.zip`（解压后双击 `index.html` 或 `启动.bat` 即可）；
> ② `公考职位查询_单文件版_日期.html`（**自带数据的一个 HTML 文件**，微信/邮件直接发给任何人都能双击打开）。
> 打包脚本会自检条目名（含中文）能否正确解压，避免出现乱码文件名。

---

## 三、本地开发与环境细节

### 手动起服务（等价于 启动.bat）

```bash
cd gongkao-job-query
python -m http.server 8000
# 浏览器打开 http://localhost:8000
```

### 自检 / 用示例夹具做回归

```bash
python tools/make_sample_excel.py                 # 生成两份虚构的示例职位表
python scraper.py --selftest                      # 离线自检：不联网，验证解析与匹配规则
node tools/smoke_test_frontend.mjs                # 前端逻辑冒烟测试（21 项断言）
python tools/build_standalone.py --check           # 检查 index.html 内嵌数据是否与 data.json 同步
```

---

## 四、生成真实数据

### 方式 A：联网自动抓取（GitHub Actions 用的就是这条）

```bash
pip install -r requirements.txt
python scraper.py                     # 抓取官方渠道 -> 生成 data.json
python scraper.py --check-only        # 只检查有没有新的职位表附件，不下载
python scraper.py --dry-run           # 解析但不写文件
python scraper.py --verbose           # 输出详细日志（含字段映射）
python scraper.py --selftest          # 离线自检：不联网，验证解析与匹配逻辑
```

抓取对象（全部为官方渠道，且有域名白名单）：

| 考试类型 | 官方渠道 |
| --- | --- |
| 国考 | 国家公务员局「中央机关及其直属机构考试录用公务员专题」（`bm.scs.gov.cn`）"相关下载"栏目、`scs.gov.cn` |
| 江苏省考 | 江苏先锋网（`www.jszzb.gov.cn`）、江苏省人力资源和社会保障厅（`jshrss.jiangsu.gov.cn`） |
| 江苏省考（市级） | 南京/苏州/无锡/常州/南通/扬州/泰州/盐城/镇江/淮安/宿迁/徐州/连云港 人社局官网 |

**抓取行为规范**：只访问上述白名单域名；遵守 `robots.txt`（禁止的链接直接跳过并记录）；同一域名请求间隔默认 **3 秒**
（若对方声明 `Crawl-delay` 则取更大值，可用 `--delay` 调整）；失败重试采用指数退避；只下载职位表附件，不抓取个人信息。

### 方式 B：本地兜底（**最稳，强烈推荐**）

政府网站常年对境外 IP、数据中心 IP 限制访问，GitHub Actions 的运行器在境外，定时任务**可能长期抓不到数据**。
这种情况下不必等待，直接：

```bash
# 1) 用浏览器打开官方公告页，手动下载职位表 Excel（.xlsx/.xls）
# 2) 用本地文件生成 data.json：
python scraper.py \
    --local "2026江苏省考职位表.xlsx" \
    --exam-type 江苏省考 \
    --year 2026 \
    --source-url "https://www.jszzb.gov.cn/xxx/公告原文.html"

# 一次传多个文件也可以（会自动合并、按"考试类型+年度+职位代码"去重）
python scraper.py --local 省考职位表.xlsx 国考职位表.xlsx --exam-type 江苏省考 --year 2026

# 3) 同步进 index.html（保证双击打开也能看到新数据）
python tools/build_standalone.py

# 4) 提交回仓库，Pages 会自动更新
git add data.json index.html && git commit -m "data: 更新 2026 江苏省考职位表" && git push
```

> **不想敲命令**：把 Excel 直接拖到 `更新数据.bat` 上即可，第 2~3 步会自动完成。

**安全阀**：本次抓取若一条数据都没拿到，`scraper.py` **绝不会覆盖**已有 `data.json`（退出码 2，并打印明确原因与操作建议）。

### 常用参数

| 参数 | 说明 |
| --- | --- |
| `--local <xlsx...>` | 用本地官方职位表生成数据（可多个文件） |
| `--exam-type` / `--year` / `--source-url` / `--source-name` | 配合 `--local` 标注来源信息 |
| `--scope jiangsu-biology` \| `all` | 收录范围：默认只收"江苏 + 与生物科学相关"；`all` 为全量 |
| `--delay <秒>` | 同一域名请求最小间隔，默认 3 |
| `--max-pages <N>` | 每个数据源最多访问页面数，默认 40 |
| `--no-merge` | 不合并历史数据，直接用本次结果覆盖 |
| `--data-status sample` | 把数据标记为示例（每条记录加 `是否示例: true`，前端显示红色角标） |
| `--check-only` / `--dry-run` / `--selftest` / `--verbose` | 只检查 / 只解析 / 离线自检 / 详细日志 |

---

## 五、部署到 GitHub Pages（自动更新 + 在线访问）

1. 新建一个 GitHub 仓库（建议 **Public**，Pages 免费；Private 需 Pro 才能用 Pages）。
2. 把本项目**全部文件**推上去（注意保留 `.github/workflows/update.yml` 与 `.nojekyll`）：

   ```bash
   git init
   git add -A
   git commit -m "feat: 公考职位查询工具"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```

3. 打开仓库 **Settings → Actions → General → Workflow permissions**，选择 **Read and write permissions**（否则机器人无法提交 data.json）。
4. 打开 **Settings → Pages → Build and deployment → Source**，选择 **GitHub Actions**。
5. 打开 **Actions** 标签页，选中「自动更新公考职位数据」→ **Run workflow** 手动跑一次，确认能成功。
6. 访问地址：`https://<你的用户名>.github.io/<仓库名>/`（页面会通过 fetch 自动读取同目录 `data.json`）。

定时任务：`.github/workflows/update.yml` 中 `cron: '0 2 * * *'`（UTC）= **北京时间每天 10:00**。
若当天没有新职位表或官网限制访问，任务只打 warning、保留旧数据，不会把仓库搞脏。

> 建议第一次部署后先手动运行一次；`workflow_dispatch` 还支持 `dry_run`、`delay`、`scope` 三个输入参数，方便调试。

---

## 六、`data.json` 数据格式

顶层结构（前端**同时兼容**纯数组格式 `[ {...}, {...} ]`）：

```json
{
  "meta": {
    "last_update": "2026-10-01T10:20:28+08:00",
    "last_update_text": "2026-10-01 10:20（北京时间）",
    "data_status": "sample | official | local-import",
    "record_count": 8,
    "new_records": 3,
    "updated_records": 0,
    "scope": "jiangsu-biology",
    "exam_types": ["国考", "江苏省考"],
    "sources": [{ "source_name": "...", "exam_type": "国考", "file": "...", "url": "...", "records": 3, "fetched_at": "..." }],
    "warnings": ["..."],
    "disclaimer": "数据来自官方公开职位表，仅供筛选参考……"
  },
  "jobs": [ { "考试类型": "江苏省考", "年度": 2026, "...": "..." } ]
}
```

页面顶部的「数据最后更新」读取自 `meta.last_update_text`（纯数组格式时，会退化为取所有记录 `抓取时间` 的最大值）。

### 职位对象字段（前端表格 / CSV 导出顺序）

| 字段 | 说明 |
| --- | --- |
| `考试类型` | 国考 / 江苏省考 / 江苏省考(某市) |
| `年度` | 招录年度，如 2026 |
| `职位代码` | 官方职位代码（唯一键的一部分） |
| `招录机关` | 招录机关 / 部门名称 |
| `用人司局/单位` | 用人司局、用人单位、内设机构 |
| `职位名称` | 招考职位名称 |
| `招录人数` | 计划录用人数 |
| `工作地点` | 工作地点 / 职位分布 |
| `学历要求` | 学历要求原文（如"本科及以上""硕士研究生及以上"） |
| `学位要求` | 学位要求原文 |
| `专业要求原文` | **官方专业要求原文，逐字保留，不做改写** |
| `专业目录归属` | 由专业原文自动打标签：`生物科学` / `生物科学类` / `基础理学类` / `教育类` / `不限专业` / `相近专业` |
| `政治面貌` | 政治面貌要求 |
| `基层工作最低年限` | 无 / 满1年 / 满2年 / 满3年 |
| `身份要求` | 应届 / 应届-择业期内 / 往届 / 不限（职位表无该列时从备注推导） |
| `户籍/生源要求` | 户籍或生源地限制 |
| `其他条件` | 其他报考条件（教师资格证等硬性要求常在此列） |
| `考试类别` | A类 / B类 / C类、专业科目等 |
| `面试比例` | 面试人选比例 |
| `备注` | 官方备注原文 |
| `咨询电话` | 招录单位咨询电话 |
| `来源链接` | 该职位表所在**官方公告页地址** |
| `来源文件` / `数据来源` / `抓取时间` | 溯源信息 |
| `匹配结论` | A / B / C / D（见下节） |
| `匹配说明` | 结论的文字依据 |
| `需电话咨询` | `否` 或需要咨询的原因（详见下节） |

---

## 七、匹配结论规则（A / B / C / D）

> 前端会用 `data.json` 中的**原始字段重新计算**结论，规则与 `scraper.py` 完全一致（`--selftest` 可验证）。

| 结论 | 含义 | 判定规则 |
| --- | --- | --- |
| **A 完全匹配** | 专业目录明确包含 | 专业原文含「生物科学」（不含"生物科学类"三字的精确匹配）或「生物科学类」或「基础理学类」，且学历允许本科报考，且岗位未额外要求师范类/教师资格证 |
| **B 可能匹配 / 需核实** | 需要打电话确认 | 属于「教育类 / 教育学类 / 学科教学」；或专业匹配但**额外要求师范类 / 教师资格证** |
| **C 不限专业** | 任何专业可报 | 专业原文为"不限专业 / 专业不限 / 不作专业限制" |
| **D 条件不符但相近** | 仅供参考 | 专业相近（如生物技术、生物工程、生态学）但未被明确列入目录；或学历要求为硕士研究生及以上等硬条件不符 |

### 「需电话咨询招录单位」标注规则

只要出现下列任一情况，该条记录都会显示 `⚠ 需电话咨询招录单位` 并给出具体原因：

1. 专业要求原文中出现「师范」字样（**毕业证专业名称为「生物科学（师范）」时，各省专业目录认定口径不同**，是否等同于"生物科学"必须由招录单位确认）；
2. 岗位要求师范类；
3. 岗位要求教师资格证（含"高级中学生物学科教师资格证"等具体表述）；
4. 匹配结论不是 A（B/C/D 一律提示核实）。

---

## 八、前端功能一览

| 功能 | 说明 |
| --- | --- |
| 零配置启动 | 双击 `index.html` 即可用：读不到 `data.json` 时自动退回到**页面内置数据**（由 `tools/build_standalone.py` 同步），不联网、不装 Python |
| 一键本地服务 | 双击 `启动.bat`（或 `bash start.sh`）自动起服务并打开浏览器，此时可自动读取最新 `data.json`；支持 `--lan` 用手机访问 |
| 自动读取 | 通过 `fetch` 读取同目录 `data.json`；失败时给出明确原因与三种解决方案 |
| 手动上传 | 支持 `data.json`、Excel（SheetJS，优先同目录 `xlsx.full.min.js`，其次 CDN）、CSV（内置解析器，无需联网） |
| 考试类型 | 国考 / 江苏省考（选项**从数据动态生成**，国考数据一接入就自动出现） |
| 省份筛选 | 国考岗位分布全国，可按省份收窄；江苏的区县/县级市会**自动归到江苏** |
| 城市筛选 | 13 个设区市 + 省级机关（`jiangsu_regions.json` 把宜兴市/江阴市/涟水县等归到所属市） |
| 咨询电话 | 从官方《招录单位咨询电话》Word 表按 (城市,单位) 回填，覆盖率约 68% |
| 年度策略 | 只保留每类考试最新年度；新年度发布后旧年度自动替换（`--year-policy keep-all` 可留历年） |
| 新表探针 | `检查新职位表.bat` / `tools/probe_new_cycle.py`：点名检查新年度是否已发布 |
| 新表提醒 | `安装提醒.bat`：每天 10:30 自动检查，**发现就弹窗**；点「是」立刻抓取更新 |
| 筛选条件 | 工作地点（默认勾选**江苏**）、学历（默认**本科**）、专业匹配（生物科学/生物科学类/基础理学类/教育类/不限专业/相近专业，默认全选）、身份（应届/择业期/往届/不限）、政治面貌（中共党员/共青团员/群众/不限）、基层工作经历（无/满1年/满2年/满3年）、其他（教师资格证、师范类、匹配结论、不需电话咨询）、关键词搜索 |
| 预计命中数 | 每个筛选项旁显示在当前其他条件下可命中的条数，避免"筛到 0 条"的无效操作 |
| 结果展示 | 桌面端 23 列表格（横向滚动 + 表头吸顶）；手机端自动切换为卡片视图，字段完整可读 |
| 每条必备信息 | **专业要求原文**、**来源链接**、**匹配结论 + 匹配说明 + 需电话咨询提示** |
| 导出 | 「导出当前筛选结果 CSV」，带 UTF-8 BOM，Excel 直接打开不乱码，另附`匹配结论/匹配说明/需电话咨询`三列 |
| 性能保护 | 单次最多渲染 500 行（防止手机卡顿），**CSV 导出不受限制**；大数据量时自动关闭"预计命中数"统计 |
| 其他 | 顶部显示数据最后更新时间与数据来源；一键重置筛选；一键收起筛选面板；打印样式（可另存为 PDF） |
| 便于分发 | `python tools/build_standalone.py --out 单文件版.html` 可导出一个自带数据的独立 HTML，发给谁都能双击打开 |

---

## 九、常见问题（FAQ）

**Q1：双击打开后提示"已自动载入页面内置数据"？**
这不是故障，而是预期行为：浏览器在 `file://` 下禁止读取本地 `data.json`，页面于是用内置数据兜底，功能完全可用。
想让页面自动读取最新 `data.json`，任选一种：① 双击 `启动.bat`；② 点「选择 data.json」手动载入；
③ 部署到 GitHub Pages。若看到的是红色报错而不是黄色提示，说明连内置数据都没有，请执行 `python tools/build_standalone.py` 重新内嵌。

**Q1.5：更新了 data.json，为什么双击打开还是旧数据？**
`index.html` 里的内置数据需要重新同步一次：执行 `python tools/build_standalone.py`
（或直接把职位表拖到 `更新数据.bat` 上，它会自动同步）。用 `启动.bat` / GitHub Pages 时以 `data.json` 为准，不受此影响。

**Q2：GitHub Actions 每天跑，但 data.json 一直不更新？**
按顺序排查：
1. 是否到了发布期？国考职位表通常 **10 月中下旬**（报名期）发布，江苏省考通常 **10—11 月**发布，其余时间官网没有新职位表，属正常；
2. 看 Actions 日志里的 warning：若显示"打开失败"，多为境外 IP 被官网限制 —— 这是最常见原因，请使用 **方式 B（本地兜底）**；
3. 仓库 Settings → Actions → General 是否为 **Read and write**（否则无法提交）；
4. 附件若是 `.rar`，脚本会提示跳过（Python 标准库不支持 rar），请手动解压后用 `--local` 传入。

**Q3：为什么有些岗位的专业原文看着能报，却被判为 D？**
D 的判定是"专业目录未明确包含"。各省专业目录对专业名称的归类口径不同（尤其带「师范」后缀），本工具无法代替招录单位认定，
请按页面提示**打电话咨询**，并以官方答复为准。

**Q4：数据会不会有错？**
所有字段均直接来自官方职位表原文，脚本不做语义改写；但官方表结构每年变化，表头映射或年度识别可能出错。
请以**来源链接**中的官方公告与职位表原件为准，发现偏差可通过 Issue 反馈。

**Q5：`downloads/` 目录要不要提交到仓库？**
不需要，已在 `.gitignore` 中忽略（Actions 会以 artifact 形式保留 7 天便于人工核对）。

---

## 十、合规与操守说明

- 只访问官方渠道域名（白名单机制，非白名单链接一律跳过）；
- 遵守 `robots.txt`，被禁止的路径跳过并记录到 `meta.warnings`；
- 请求频率默认 ≥3 秒/次，并遵守对方声明的 `Crawl-delay`；失败重试采用指数退避；
- 只下载公开发布的职位表附件，不采集任何个人信息、不绕过任何访问控制、不做验证码识别；
- **绝不编造数据**：抓不到就保留旧数据并把原因写进日志与 `meta.warnings`，首次运行抓不到时宁可不生成 `data.json`。

## 十一、免责声明

本工具仅用于**辅助筛选**，不构成报考建议。职位表字段、专业目录归类、报考资格最终以官方公告、职位表原件及招录单位答复为准。
使用本工具产生的任何后果由使用者自行承担。
