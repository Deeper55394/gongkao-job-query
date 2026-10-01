# ============================================================================
#  manage_reminder.ps1 —— 安装 / 卸载 / 查看「新职位表提醒」计划任务
# ============================================================================
#  用法（一般由 安装提醒.bat / 取消提醒.bat 调用）：
#      powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action install
#      powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action remove
#      powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action status
#      powershell -ExecutionPolicy Bypass -File tools\manage_reminder.ps1 -Action test
#
#  说明：任务只在**你登录时**运行（这样才能弹窗提醒），每天一次，默认 10:30。
#        不需要管理员权限（注册在当前用户下）。
#  ⚠ 本文件必须保存为「UTF-8 带 BOM」。
# ============================================================================

param(
    [ValidateSet('install', 'remove', 'status', 'test', 'run')]
    [string]$Action = 'status',
    [string]$Time = '10:30'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$taskName = '公考职位查询-新表提醒'
$worker = Join-Path $projectRoot 'tools\remind_new_cycle.ps1'
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

Write-Host ''
Write-Host '公考职位查询 · 新职位表提醒' -ForegroundColor Cyan
Write-Host ('项目目录：{0}' -f $projectRoot)

switch ($Action) {

    'install' {
        if (-not (Test-Path $worker)) {
            Write-Host ('[错误] 找不到 {0}' -f $worker) -ForegroundColor Red
            exit 1
        }
        $arg = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $worker
        # ⚠ 变量名不能叫 $action：PowerShell 变量名大小写不敏感，
        #   会与 param 里的 [ValidateSet]$Action 撞车并报 ValidateSetFailure。
        $taskAction = New-ScheduledTaskAction -Execute $ps -Argument $arg
        $taskTrigger = New-ScheduledTaskTrigger -Daily -At $Time
        $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
        $taskPrincipal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
            -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger `
            -Settings $taskSettings -Principal $taskPrincipal -Force `
            -Description '每天检查官方是否发布新年度公务员职位表；发现后弹窗提醒，可一键抓取更新' | Out-Null
        Write-Host ('[已安装] 计划任务「{0}」每天 {1} 自动检查一次' -f $taskName, $Time) -ForegroundColor Green
        Write-Host '         发现新职位表会弹窗提醒；点「是」即可立刻更新。'
        Write-Host '         记录文件：提醒记录.log'
    }

    'remove' {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host ('[已移除] 计划任务「{0}」' -f $taskName) -ForegroundColor Green
        } else {
            Write-Host '[提示] 该计划任务本来就没有安装。' -ForegroundColor Yellow
        }
    }

    'status' {
        $t = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if (-not $t) {
            Write-Host '[状态] 未安装提醒（双击 安装提醒.bat 即可添加）' -ForegroundColor Yellow
            exit 0
        }
        $info = Get-ScheduledTaskInfo -TaskName $taskName
        Write-Host '[状态] 已安装' -ForegroundColor Green
        Write-Host ('       状态：{0}' -f $t.State)
        Write-Host ('       上次运行：{0}（结果 0x{1:X}）' -f $info.LastRunTime, $info.LastTaskResult)
        Write-Host ('       下次运行：{0}' -f $info.NextRunTime)
        $log = Join-Path $projectRoot '提醒记录.log'
        if (Test-Path $log) {
            Write-Host '       最近 5 条记录：'
            Get-Content -LiteralPath $log -Tail 5 | ForEach-Object { Write-Host ('         {0}' -f $_) }
        }
    }

    'test' {
        Write-Host '[测试] 立刻弹一次提醒窗口…' -ForegroundColor Cyan
        & $ps -NoProfile -ExecutionPolicy Bypass -File $worker -Test
        $log = Join-Path $projectRoot '提醒记录.log'
        if (Test-Path $log) { Get-Content -LiteralPath $log -Tail 3 | ForEach-Object { Write-Host ('   ' + $_) } }
    }

    'run' {
        Write-Host '[运行] 立刻按真实逻辑检查一次（不会弹窗，除非真发现新表）…' -ForegroundColor Cyan
        & $ps -NoProfile -ExecutionPolicy Bypass -File $worker
        $log = Join-Path $projectRoot '提醒记录.log'
        if (Test-Path $log) { Get-Content -LiteralPath $log -Tail 3 | ForEach-Object { Write-Host ('   ' + $_) } }
    }
}
Write-Host ''
