# ============================================================================
#  make_shortcut.ps1 —— 在桌面创建"公考职位查询"快捷方式
# ============================================================================
#  被 创建桌面快捷方式.bat 调用，也可以直接右键"使用 PowerShell 运行"：
#      powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
#      powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1 update
#      powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1 both
#
#  说明：本文件必须保存为「UTF-8 带 BOM」，否则 Windows PowerShell 5.1
#        会按 ANSI 读取，中文会变乱码。
# ============================================================================

param(
    [ValidateSet('main', 'update', 'probe', 'both', 'all')]
    [string]$Which = 'main',
    [string]$DesktopPath = ''          # 仅用于测试时指定其他目录
)

$ErrorActionPreference = 'Stop'

# —— 定位项目目录（本脚本位于 <项目>\tools\）——
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $projectRoot 'index.html'))) {
    Write-Host "[错误] 未能在 $projectRoot 找到 index.html，请保持目录结构不变。" -ForegroundColor Red
    exit 1
}

# —— 桌面目录（自动适配 OneDrive 重定向）——
if ([string]::IsNullOrWhiteSpace($DesktopPath)) {
    $DesktopPath = [Environment]::GetFolderPath('Desktop')
}
if (-not (Test-Path $DesktopPath)) {
    Write-Host "[错误] 桌面目录不存在：$DesktopPath" -ForegroundColor Red
    exit 1
}

$iconPath = Join-Path $projectRoot 'icon.ico'
$hasIcon = Test-Path $iconPath

# —— 从 data.json 读取当前数据概况，让快捷方式提示文字始终与实际数据一致 ——
$dataDesc = '公考职位查询（国考 + 江苏省考）· 双击打开，自动同步最新官方数据'
$dataFile = Join-Path $projectRoot 'data.json'
if (Test-Path $dataFile) {
    try {
        $dj = Get-Content -LiteralPath $dataFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $jobs = $dj.jobs
        if ($jobs -and $jobs.Count -gt 0) {
            $byType = $jobs | Group-Object -Property 考试类型 | Sort-Object Name
            $parts = @()
            foreach ($g in $byType) { $parts += ('{0} {1} 条' -f $g.Name, $g.Count) }
            $dataDesc = ('公考职位查询（{0}）· 共 {1} 条官方职位 · 双击打开并自动同步最新数据' -f
                         ($parts -join ' + '), $jobs.Count)
            $stamp = ''
            if ($dj.meta -and $dj.meta.last_update_text) { $stamp = [string]$dj.meta.last_update_text }
            if ($stamp) { $dataDesc = $dataDesc + '｜数据更新：' + $stamp }
        }
    } catch {
        Write-Host ("[提示] 读取 data.json 失败，快捷方式将使用通用说明：{0}" -f $_.Exception.Message) -ForegroundColor Yellow
    }
}

# —— 快捷方式定义 ——
# WindowStyle：7 = 最小化（启动服务的黑窗口不挡事），1 = 正常（需要交互输入）
$defs = @(
    @{
        Key      = 'main'
        Name     = '公考职位查询.lnk'
        Target   = Join-Path $projectRoot '启动.bat'
        Desc     = $dataDesc
        Style    = 7
    },
    @{
        Key      = 'update'
        Name     = '更新公考职位数据.lnk'
        Target   = Join-Path $projectRoot '更新数据.bat'
        Desc     = '把官方职位表 Excel 拖到本快捷方式上，即可更新 data.json（省考 / 国考都支持）'
        Style    = 1
    },
    @{
        Key      = 'probe'
        Name     = '检查公考新职位表.lnk'
        Target   = Join-Path $projectRoot '检查新职位表.bat'
        Desc     = '检查官方是否已发布新年度（如 2027）职位表；发现后可直接自动更新'
        Style    = 1
    }
)

$want = switch ($Which) {
    'both' { @('main', 'update') }
    'all'  { @('main', 'update', 'probe') }
    default { @($Which) }
}
$shell = New-Object -ComObject WScript.Shell
$created = 0

Write-Host ""
Write-Host "公考职位查询工具 · 创建桌面快捷方式" -ForegroundColor Cyan
Write-Host ("项目目录：{0}" -f $projectRoot)
Write-Host ("桌面目录：{0}" -f $DesktopPath)
Write-Host ""

foreach ($d in $defs) {
    if ($want -notcontains $d.Key) { continue }

    if (-not (Test-Path $d.Target)) {
        Write-Host ("[跳过] 找不到 {0}" -f $d.Target) -ForegroundColor Yellow
        continue
    }

    $linkPath = Join-Path $DesktopPath $d.Name
    $exists = Test-Path $linkPath

    $sc = $shell.CreateShortcut($linkPath)
    $sc.TargetPath       = $d.Target
    $sc.WorkingDirectory = $projectRoot
    $sc.Description      = $d.Desc
    $sc.WindowStyle      = $d.Style
    if ($hasIcon) { $sc.IconLocation = ("{0},0" -f $iconPath) }
    $sc.Save()

    if ($exists) {
        Write-Host ("[已更新] {0}" -f $linkPath) -ForegroundColor Green
    } else {
        Write-Host ("[已创建] {0}" -f $linkPath) -ForegroundColor Green
    }
    Write-Host ("         指向：{0}" -f $d.Target)
    $created++
}

if (-not $hasIcon) {
    Write-Host "[提示] 没找到 icon.ico，快捷方式将使用系统默认图标。" -ForegroundColor Yellow
    Write-Host "       可在项目目录执行：python tools/make_icon.py 重新生成。" -ForegroundColor Yellow
}

Write-Host ""
if ($created -gt 0) {
    Write-Host ("完成：共处理 {0} 个快捷方式，回到桌面即可看到。" -f $created) -ForegroundColor Green
    Write-Host "提示：如果移动了项目文件夹，重新双击 创建桌面快捷方式.bat 即可修复。" -ForegroundColor Gray
    exit 0
} else {
    Write-Host "[错误] 没有创建任何快捷方式。" -ForegroundColor Red
    exit 1
}
