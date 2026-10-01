# ============================================================================
#  tools/deploy_github.ps1 —— 把本项目推送到你的 GitHub 仓库（用来开 GitHub Pages）
# ============================================================================
#  由 部署到GitHub.bat 调用，也可以直接命令行运行：
#      powershell -ExecutionPolicy Bypass -File tools\deploy_github.ps1
#      powershell -ExecutionPolicy Bypass -File tools\deploy_github.ps1 -Check
#      powershell -ExecutionPolicy Bypass -File tools\deploy_github.ps1 -RepoUrl https://github.com/me/gongkao-job-query.git
#
#  它会做：检查 git → 配置提交身份 → git init/add/commit → 添加远程仓库 → 推送 main
#  它不会：替你登录 GitHub（第一次 push 会弹出登录窗口，用浏览器授权即可）
#
#  注意：本文件必须保存为「UTF-8 带 BOM」，否则 Windows PowerShell 5.1 读中文会乱码。
# ============================================================================

param(
    [string]$RepoUrl = '',
    [string]$RepoName = 'gongkao-job-query',
    [string]$UserName = '',
    [switch]$Check
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

function Write-Title($t) {
    Write-Host ''
    Write-Host ('=' * 66) -ForegroundColor DarkGray
    Write-Host $t -ForegroundColor Cyan
    Write-Host ('=' * 66) -ForegroundColor DarkGray
}
function Write-Step($t) { Write-Host ('  -> ' + $t) -ForegroundColor White }
function Write-Ok($t)   { Write-Host ('  [OK] ' + $t) -ForegroundColor Green }
function Write-Warn2($t) { Write-Host ('  [!] ' + $t) -ForegroundColor Yellow }
function Write-Err2($t)  { Write-Host ('  [x] ' + $t) -ForegroundColor Red }

# --------------------------------------------------------------------------- #
# 0. 环境检查（PATH 里没有 git 就翻常见安装目录——刚装完 Git 时新窗口常读不到新 PATH）
# --------------------------------------------------------------------------- #
function Resolve-GitExe {
    $g = Get-Command git -ErrorAction SilentlyContinue
    if ($g) { return $g.Source }
    $cands = @(
        (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd\git.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe')
    )
    foreach ($c in $cands) {
        if ($c -and (Test-Path $c)) {
            $env:PATH = (Split-Path $c) + ';' + $env:PATH
            return $c
        }
    }
    return ''
}

Write-Title '公考职位查询工具 · 部署到 GitHub Pages'

if (-not (Test-Path (Join-Path $projectRoot 'index.html'))) {
    Write-Err2 ('没找到 index.html，请保持目录结构不变：' + $projectRoot)
    exit 1
}

$gitExe = Resolve-GitExe
if (-not $gitExe) {
    Write-Err2 '没有检测到 git，无法推送。'
    Write-Host ''
    Write-Host '请先安装 Git for Windows（一路默认下一步即可）：' -ForegroundColor Yellow
    Write-Host '    https://git-scm.com/download/win' -ForegroundColor White
    Write-Host '    （或用 winget 一条命令安装： winget install --id Git.Git -e）' -ForegroundColor Gray
    Write-Host ''
    Write-Host '装完请关闭本窗口，重新双击 部署到GitHub.bat。' -ForegroundColor Yellow
    Write-Host '（不想装 git 也可以：用网页版「拖拽上传」的办法，见 部署到GitHub Pages.md）' -ForegroundColor Gray
    if (-not $Check) { Start-Process 'https://git-scm.com/download/win' }
    exit 1
}
$gitVersion = (& git --version) 2>&1
Write-Ok ("git 可用：" + $gitVersion + '   (' + $gitExe + ')')

# --------------------------------------------------------------------------- #
# 1. -Check 模式：只看状态，不动任何东西
# --------------------------------------------------------------------------- #
if ($Check) {
    Write-Host ''
    Write-Step ('项目目录 : ' + $projectRoot)
    Write-Step ('是否已 git init : ' + (Test-Path (Join-Path $projectRoot '.git')))
    if (Test-Path (Join-Path $projectRoot '.git')) {
        $remote = (& git remote get-url origin 2>$null)
        Write-Step ('origin   : ' + ($(if ($remote) { $remote } else { '(未设置)' })))
        $branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
        Write-Step ('当前分支 : ' + $branch)
        Write-Step ('提交数量 : ' + (& git rev-list --count HEAD 2>$null))
    }
    Write-Step ('user.name : ' + (& git config --global user.name))
    Write-Step ('user.email: ' + (& git config --global user.email))
    Write-Host ''
    Write-Ok '检查完成（未做任何修改）'
    exit 0
}

# --------------------------------------------------------------------------- #
# 2. 提交身份（没配过就问一次）
# --------------------------------------------------------------------------- #
$curName = (& git config --global user.name) 2>$null
if ([string]::IsNullOrWhiteSpace($curName)) {
    $answer = Read-Host '请输入你的名字（仅用于 git 提交记录，随便填）'
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = $env:USERNAME }
    & git config --global user.name $answer | Out-Null
    Write-Ok ('user.name = ' + $answer)
}
$curMail = (& git config --global user.email) 2>$null
if ([string]::IsNullOrWhiteSpace($curMail)) {
    $answer = Read-Host '请输入你的邮箱（仅用于 git 提交记录，随便填，如 me@example.com）'
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = 'me@example.com' }
    & git config --global user.email $answer | Out-Null
    Write-Ok ('user.email = ' + $answer)
}

# --------------------------------------------------------------------------- #
# 3. 本地仓库初始化与提交
# --------------------------------------------------------------------------- #
Write-Host ''
Write-Step '准备本地仓库…'
if (-not (Test-Path (Join-Path $projectRoot '.git'))) {
    & git init | Out-Null
    Write-Ok 'git init 完成'
} else {
    Write-Ok '已存在 .git，沿用'
}
& git add -A | Out-Null
$pending = (& git status --porcelain)
if ($pending) {
    & git commit -m ('deploy: 部署公考职位查询工具 ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-Null
    Write-Ok '已创建提交'
} else {
    Write-Ok '没有新改动，跳过提交'
}
& git branch -M main 2>$null | Out-Null
Write-Ok '分支已设为 main'

# --------------------------------------------------------------------------- #
# 4. 远程仓库地址
# --------------------------------------------------------------------------- #
$gh = Get-Command gh -ErrorAction SilentlyContinue
$existingRemote = (& git remote get-url origin 2>$null)

if ([string]::IsNullOrWhiteSpace($RepoUrl) -and $existingRemote) { $RepoUrl = $existingRemote }

if ([string]::IsNullOrWhiteSpace($RepoUrl)) {
    Write-Host ''
    Write-Host '请先在浏览器里新建一个空仓库（不要勾选 Add README / .gitignore）：' -ForegroundColor Yellow
    Write-Host '    https://github.com/new' -ForegroundColor White
    Write-Host ('  仓库名建议：' + $RepoName + '    可见性：Public（私有仓库用 Pages 需要付费账号）') -ForegroundColor Gray
    Write-Host ''
    if (-not $UserName) { $UserName = Read-Host '你的 GitHub 用户名（例如 zhangsan，可留空跳过）' }
    if ($UserName) {
        $RepoUrl = 'https://github.com/' + $UserName + '/' + $RepoName + '.git'
        Write-Host ('  将使用：' + $RepoUrl) -ForegroundColor Gray
    } else {
        $RepoUrl = Read-Host '请粘贴仓库地址（形如 https://github.com/用户名/仓库名.git）'
    }
}

if ([string]::IsNullOrWhiteSpace($RepoUrl)) {
    Write-Err2 '没有拿到仓库地址，已停止（本地提交已经做好，随时可以再跑一次）。'
    exit 1
}

# 从 URL 推出 Pages 地址，稍后提示用
$pagesUrl = ''
if ($RepoUrl -match 'github\.com[:/]+([^/]+)/([^/]+?)(\.git)?$') {
    $owner = $Matches[1]
    $repo = $Matches[2]
    $pagesUrl = 'https://' + $owner + '.github.io/' + $repo + '/'
    $settingsActions = 'https://github.com/' + $owner + '/' + $repo + '/settings/actions'
    $settingsPages = 'https://github.com/' + $owner + '/' + $repo + '/settings/pages'
    $actionsPage = 'https://github.com/' + $owner + '/' + $repo + '/actions'
}

if ($existingRemote) {
    & git remote set-url origin $RepoUrl | Out-Null
    Write-Ok ('origin 已更新为 ' + $RepoUrl)
} else {
    & git remote add origin $RepoUrl | Out-Null
    Write-Ok ('origin 已添加：' + $RepoUrl)
}

# --------------------------------------------------------------------------- #
# 5. 推送（第一次会弹出 GitHub 登录窗口）
# --------------------------------------------------------------------------- #
Write-Host ''
Write-Step '开始推送（第一次会弹出登录窗口，请用浏览器授权你的 GitHub 账号）…'
& git push -u origin main
$pushCode = $LASTEXITCODE

Write-Host ''
if ($pushCode -ne 0) {
    Write-Err2 '推送失败。常见原因：'
    Write-Host '    1) 还没建仓库，或仓库名/用户名写错 → 到 https://github.com/new 建好后重跑本脚本' -ForegroundColor Yellow
    Write-Host '    2) 远程已有内容（建仓库时勾了 README）→ 先执行： git pull --rebase origin main   再重跑' -ForegroundColor Yellow
    Write-Host '    3) 登录窗口被关掉了 → 重跑本脚本，重新授权即可' -ForegroundColor Yellow
    exit 1
}
Write-Ok '推送成功！'

# --------------------------------------------------------------------------- #
# 6. 剩下的两步（只能你来点）
# --------------------------------------------------------------------------- #
Write-Host ''
Write-Host ('=' * 66) -ForegroundColor Green
Write-Host ' 代码已上传成功，还差两步设置（都只需点一次）：' -ForegroundColor Green
Write-Host ('=' * 66) -ForegroundColor Green
Write-Host ''
Write-Host ' 第 1 步：允许机器人把新数据写回仓库' -ForegroundColor White
Write-Host '   Workflow permissions → 选 Read and write permissions → Save' -ForegroundColor Gray
if ($settingsActions) { Write-Host ('   ' + $settingsActions) -ForegroundColor Cyan }
Write-Host ''
Write-Host ' 第 2 步：开启网页托管（二选一，推荐 A）' -ForegroundColor White
Write-Host '   A. GitHub Actions：Source 选 "GitHub Actions"（用仓库自带的工作流部署）' -ForegroundColor Gray
Write-Host '   B. 分支部署     ：Source 选 "Deploy from a branch" → main / (root)' -ForegroundColor Gray
if ($settingsPages) { Write-Host ('   ' + $settingsPages) -ForegroundColor Cyan }
Write-Host ''
Write-Host ' 想立刻更新一次数据：' -ForegroundColor White
if ($actionsPage) { Write-Host ('   ' + $actionsPage + '  → 选「自动更新公考职位数据」→ Run workflow') -ForegroundColor Cyan }
Write-Host ''
Write-Host ' 设置生效后，访问地址是：' -ForegroundColor White
if ($pagesUrl) { Write-Host ('   ' + $pagesUrl) -ForegroundColor Green } else { Write-Host '   https://<用户名>.github.io/<仓库名>/' -ForegroundColor Green }
Write-Host ''
Write-Host ' 详细图文步骤见： 部署到GitHub Pages.md（或同名的 .html）' -ForegroundColor Gray
Write-Host ''

if ($settingsActions -and $settingsPages) {
    $open = Read-Host '现在帮你在浏览器打开这两个设置页吗？(Y/n)'
    if ($open -ne 'n' -and $open -ne 'N') {
        Start-Process $settingsActions
        Start-Sleep -Seconds 1
        Start-Process $settingsPages
    }
}
exit 0
