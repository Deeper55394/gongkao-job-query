# 部署到 GitHub Pages（让别人也能打开你这份职位查询工具）

> 目标：把工具传到 GitHub，用一个网址访问，并且**每天自动更新数据**。
> 全程两种做法，**推荐先看方式 A（不用装任何软件）**。

---

## 〇、先搞清楚要传什么

要传的是**仓库根目录**下这些东西（`index.html` 和 `data.json` 必须同级）：

| 必须传 | 作用 |
| --- | --- |
| `index.html` | 网页本体（已内嵌数据，打开就有内容） |
| `data.json` | 数据（网页会自动读取它，比内嵌数据优先） |
| `xlsx.full.min.js` | 让网页能离线解析 Excel（上传职位表用） |
| `icon.ico`、`.nojekyll` | 图标、GitHub Pages 配置（`.nojekyll` 是空文件，别漏） |
| `.github/workflows/update.yml` | 每天自动抓取职位表的机器人 |
| `scraper.py`、`requirements.txt`、`tools/` | 机器人运行时要用 |
| `README.md`、`使用教程.html`、`先看这里.txt` 等 | 说明文档，可选 |

我已经把上面这些打成一个**根目录结构**的压缩包，直接用这个包最省事：

```
GitHub部署包_日期.zip     ← 解压后里面的文件要放在仓库根目录（不要再套一层文件夹！）
```

> 解压后如果看到一个 `GitHub部署包` 文件夹，进去把**里面的内容**全选，才是要上传的东西。

---

## 一、方式 A：网页拖拽上传（不用装任何软件）

### 第 1 步：注册 / 登录 GitHub

打开 https://github.com ，没有账号就注册一个（免费）。

### 第 2 步：新建仓库

1. 打开 https://github.com/new ；
2. **Repository name** 填 `gongkao-job-query`（名字随意，建议用英文）；
3. **Public / Private** 选 **Public**（私有仓库用 Pages 需要付费账号）；
4. **不要**勾选 "Add a README file"、".gitignore"、"license"（保持空仓库最好传）；
5. 点 **Create repository**。

### 第 3 步：上传文件

1. 在新出现的空仓库页面，点中间那行蓝色的 **uploading an existing file**；
2. 把解压出来的**所有文件和文件夹全选**（资源管理器里 `Ctrl + A`），**拖进浏览器中间那个虚线框**；
3. 等上传列表出现（应该能看到 `index.html`、`data.json`、`tools/…`、`.github/…` 等，约 30 个文件）；
4. 在下面的 **Commit changes** 输入框里写一句 `首次上传`，点绿色按钮提交。

> 上传完成后，仓库首页应该能看到 `index.html`、`data.json`、`tools`、`.github` 等。
> 如果**看不到 `.github` 文件夹**（有些浏览器会跳过以点开头的文件夹），手动补一个：
> 点 **Add file → Create new file**，文件名填 `.github/workflows/update.yml`
> （注意：在文件名输入框里直接输入 `/` 会自动变成目录），然后把本机文件
> `.github/workflows/update.yml` 的内容整个复制粘贴进去，提交即可。

### 第 4 步：允许机器人把新数据写回仓库

1. 打开仓库的 **Settings → Actions → General**；
2. 拉到最下面 **Workflow permissions**，选 **Read and write permissions**；
3. 点 **Save**。

> 不做这一步，每天定时任务抓到的数据**没法提交回仓库**（会看到权限报错）。

### 第 5 步：开启网页托管（Pages）

1. 打开 **Settings → Pages**；
2. **Source** 二选一（**两种本项目都已实测可用**）：
   - **A. Deploy from a branch** —— Branch 选 `main`，目录选 `/ (root)`，保存。
     优点：**不依赖 Actions 能否跑成功**，每次 push 自动重新发布，最省心（本项目线上一开始就用这种）。
   - **B. GitHub Actions** —— 用仓库自带的 `update.yml` 部署（官方新方式，站点内容与抓取任务强绑定）。
     仓库自带的工作流会**自动识别**你选了哪种：分支部署时它会跳过 Actions 部署步骤，**不会天天报红**。
3. 保存后等 1～2 分钟。

### 第 6 步：访问你的网址

```
https://你的用户名.github.io/gongkao-job-query/
```

例如用户名是 `zhangsan`、仓库名是 `gongkao-job-query`，网址就是
`https://zhangsan.github.io/gongkao-job-query/` 。

打开后应该能看到工具页面，顶部「数据最后更新」显示的是 `data.json` 里的时间。

### 第 7 步（可选）：立刻跑一次自动更新

打开仓库的 **Actions** 标签 → 左侧选「自动更新公考职位数据」→ 右侧 **Run workflow** → 绿色按钮。
跑完可以点进去看日志：能抓到就更新数据，抓不到会明确提示原因（不影响网页访问）。

---

## 二、方式 B：装 Git 后双击脚本（适合以后经常更新）

### 第 1 步：安装 Git for Windows

下载 https://git-scm.com/download/win ，一路「下一步」装完（默认选项就行）。

### 第 2 步：在 GitHub 建一个空仓库

同方式 A 的第 1、2 步（记下你的**用户名**和**仓库名**）。

### 第 3 步：双击 `部署到GitHub.bat`

脚本会依次问你/自动完成：

1. 检查 git 是否可用；
2. 首次运行会问你的名字和邮箱（只是写进提交记录，随便填）；
3. 自动 `git init` → 提交全部文件 → 分支设为 `main`；
4. 问你的 GitHub 用户名，拼出仓库地址（也可以直接粘贴完整仓库地址）；
5. 执行推送 —— **第一次会弹出 GitHub 登录窗口，用浏览器授权即可**；
6. 推送成功后打印剩下要点的两个设置页地址，并可以帮你自动打开。

> 只想看看当前状态、不做任何修改：`部署到GitHub.bat -Check`

### 第 4 步：完成两个设置

同方式 A 的第 4、5 步（Actions 权限 + Pages 来源）。

---

## 三、以后怎么更新数据

| 你用什么方式部署 | 更新数据的做法 |
| --- | --- |
| 方式 A / B 都行 | **什么都不用做**：每天北京时间 10:00 机器人自动跑（前提是官网能访问到） |
| 想手动触发 | 仓库 **Actions → 自动更新公考职位数据 → Run workflow** |
| 拿到官方 Excel 想立刻更新 | ① 本机用 `更新数据.bat` 生成新 `data.json`；② 在网页上打开仓库里的 `data.json` → 点铅笔图标（Edit）→ 全选删除 → 粘贴新内容 → Commit changes |

> **重要提醒**：GitHub 的服务器在境外，政府网站常限制境外 IP 访问，所以**自动抓取可能长期失败**。
> 实测数据：一次定时任务里 17 个官方站点（国考专题、江苏先锋网、人社厅、13 个设区市人社局）**页面全部访问失败**，
> 而同一时刻在本机（国内网络）访问只要 0.3 秒 —— 这是**地域封锁，不是配置错误**。
> 这不是部署出错，遇到这种情况用下面第三节的手动办法。
> 工具抓不到数据时不会覆盖已有 `data.json`，也绝不会编造数据。

> **想让它真正每天自动更新？** 两条可行路线（都需要你点头，涉及在你电脑上做设置）：
> 1. **让更新在你的电脑上定时跑**：用自己的网络抓取 → 本地生成 data.json → 自动 `git push` 回仓库（Pages 会自动重新发布）。国内网络能访问官网，这是最省事的。
> 2. **自建 GitHub Actions 运行器（self-hosted runner）**：把 runner 装在你的电脑上，让 GitHub 的工作流在你的网络里执行，仓库里现有工作流不用改。

---

## 四、部署成功怎么验证

1. 网址能打开，页面上有筛选条件、有职位表格（即使是示例数据）；
2. 页面顶部「数据最后更新」和时间对得上；
3. 手机浏览器打开同一个网址也能用（表格会自动变成卡片）；
4. 仓库 **Actions** 里能看到「自动更新公考职位数据」的运行记录；
5. 点页面里的「导出当前筛选结果 CSV」，能下载到 CSV 文件。

---

## 五、常见问题

| 现象 | 原因与解决 |
| --- | --- |
| 打开网址是 404 | Pages 还没生效或路径不对。等 1～2 分钟；确认地址形如 `https://用户名.github.io/仓库名/`；确认 `index.html` 在仓库**根目录**而不是子文件夹里 |
| 页面能开但提示"未能自动读取 data.json" | 多半是 `data.json` 没传或不在根目录。检查仓库首页有没有 `data.json`，且与 `index.html` 同级 |
| Actions 报权限错误，改不了 data.json | 回到 Settings → Actions → General → Workflow permissions，选 **Read and write** |
| Actions 报 `Get Pages site failed` | Pages 来源没设成 GitHub Actions。要么改设置（Settings → Pages → Source = GitHub Actions），要么改成分支部署（工作流会自动跳过部署步骤） |
| 定时任务一直抓不到数据 | 境外 IP 被官网限制，属正常。用手动方式更新 `data.json`（见第三节） |
| 上传时提示文件太大 | 本项目最大文件是 `xlsx.full.min.js`（约 861 KB），远低于 25 MB 限制；若提示过大，说明你误传了别的文件 |
| 想删掉重来 | 仓库 Settings → 最下面 Delete this repository；或只删 Pages：Settings → Pages → 关闭 |
| 想用私有仓库 | GitHub Pages 对私有仓库需要付费（Pro）；免费账号请用 Public |
| 想绑自己的域名 | Settings → Pages → Custom domain 填域名，并在域名商处加 CNAME 解析到 `你的用户名.github.io`（本项目未强依赖域名，可跳过） |

---

## 六、一句话总结

1. 新建 **Public** 空仓库 → 2. 把 `GitHub部署包` 里的**内容**传到**根目录** →
3. Settings → Actions 选 **Read and write** → 4. Settings → Pages 选 **GitHub Actions**（或分支 main / root）→
5. 打开 `https://用户名.github.io/仓库名/` 即可。

之后每天自动更新；抓不到就按第三节手动更新 `data.json`，一次一分钟。
