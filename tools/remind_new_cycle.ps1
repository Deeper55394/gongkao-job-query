# ============================================================================
#  remind_new_cycle.ps1 —— 每天自动检查官方有没有发布新年度职位表
# ============================================================================
#  由计划任务「公考职位查询-新表提醒」每天调用（见 tools\manage_reminder.ps1）。
#  行为：
#    · 跑 tools\probe_new_cycle.py（轻量探测，只看几个官方页面）
#    · 没发现新年度 -> 静默，只写日志
#    · 发现新年度   -> 弹窗提醒；点「是」立刻抓取并更新（data.json + 内嵌 + 推送）
#    · 同一年度只提醒一次（状态记在 .remind-state.json）
#
#  手动测试：
#    powershell -ExecutionPolicy Bypass -File tools\remind_new_cycle.ps1 -Test
#
#  ⚠ 本文件必须保存为「UTF-8 带 BOM」。
# ============================================================================

param(
    [switch]$Test,          # 强制弹一次窗（用于验证提醒是否正常）
    [switch]$AutoUpdate     # 发现后不问，直接抓取更新
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logPath = Join-Path $projectRoot '提醒记录.log'
$statePath = Join-Path $projectRoot '.remind-state.json'

function Write-Log([string]$msg) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
    try { Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8 } catch { }
}

function Find-Python {
    foreach ($pat in @("$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
                       "$env:ProgramFiles\Python3*\python.exe")) {
        $c = Get-ChildItem $pat -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($c) { return $c.FullName }
    }
    foreach ($name in @('python', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notmatch 'WindowsApps') { return $cmd.Source }
    }
    return ''
}

$py = Find-Python
if (-not $py) {
    Write-Log '未找到 Python，跳过检查（安装 Python 后即可恢复）'
    exit 0
}

# ---- 跑探针（exit 5 = 发现新年度；0 = 尚未发布）----
$probeArgs = @((Join-Path $projectRoot 'tools\probe_new_cycle.py'), '--delay', '2')
$out = & $py @probeArgs 2>&1 | Out-String
$code = $LASTEXITCODE
$found = ($code -eq 5)

$body = ($out -split "`r?`n" | Where-Object { $_ -match '🎉|\[发现\]|尚未发现|\[20\d\d\]|·\s' } |
         Select-Object -First 12) -join "`r`n"
if (-not $body) { $body = ($out -split "`r`n" | Select-Object -First 8) -join "`r`n" }

if ($Test) {
    $found = $true
    $body = "[测试] 这是一条演示提醒。`r`n发现示例：江苏省2027年度考试录用公务员职位表`r`n（真实运行时这里会列出官方页面/附件链接）"
    Write-Log '执行了一次测试提醒'
}

if (-not $found) {
    Write-Log '尚未发现新年度职位表（正常，官方通常 10 月中下旬 ~ 11 月发布）'
    exit 0
}

# ---- 同一年度只提醒一次 ----
$fingerprint = ($body -replace '\s+', ' ').Trim()
$state = @{}
if (Test-Path $statePath) {
    try { $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $state = @{} }
}
if (-not $Test -and $state.fingerprint -eq $fingerprint) {
    Write-Log '结果与上次相同，已提醒过，跳过弹窗'
    exit 0
}
@{ fingerprint = $fingerprint; at = (Get-Date).ToString('s') } |
    ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

# ---- 弹窗（4+64 = 是/否 + 信息图标；120 秒后自动消失）----
$msg = @"
官方似乎已经发布新年度职位表了！

$body

点「是」＝现在立刻抓取更新（约 1-3 分钟，含内嵌与推送）
点「否」＝稍后自己处理（双击 检查新职位表.bat）

检查时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm')
"@
$sh = New-Object -ComObject WScript.Shell
$popupSeconds = if ($Test) { 25 } else { 120 }
$answer = $sh.Popup($msg, $popupSeconds, '公考职位查询 · 发现新年度职位表', 4 + 64)
Write-Log ("弹窗提醒已发出，用户选择={0}（6=是 7=否 -1=超时）" -f $answer)

if ($Test) { Write-Log '测试模式：只弹窗，不执行更新'; exit 0 }
if ($answer -ne 6 -and -not $AutoUpdate) { exit 0 }

# ---- 立刻更新 ----
Write-Log '开始自动更新（抓取 -> 内嵌 -> 推送）'
Push-Location $projectRoot
try {
    & $py 'scraper.py' '--time-budget' '900' 2>&1 | Out-Null
    $scrapeCode = $LASTEXITCODE
    Write-Log ("scraper 退出码={0}" -f $scrapeCode)
    if ($scrapeCode -eq 0 -or $scrapeCode -eq 2) {
        & $py 'tools\build_standalone.py' 2>&1 | Out-Null
        $git = (Get-Command git -ErrorAction SilentlyContinue).Source
        if (-not $git -and (Test-Path "$env:ProgramFiles\Git\cmd\git.exe")) {
            $git = "$env:ProgramFiles\Git\cmd\git.exe"
        }
        if ($git) {
            & $git add -A 2>&1 | Out-Null
            & $git commit -m 'chore(data): 新年度职位表自动更新（提醒任务触发）' 2>&1 | Out-Null
            & $git push 2>&1 | Out-Null
            Write-Log ("已提交并推送，git 退出码={0}" -f $LASTEXITCODE)
        } else {
            Write-Log '未找到 git，数据已抓取但未推送（请手动 push 或装 Git）'
        }
    } else {
        Write-Log '抓取未取到数据（保留原有数据，未做改动）'
    }
} finally {
    Pop-Location
}
Write-Log '本次提醒任务结束'
exit 0
