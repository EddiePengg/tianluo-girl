# pt2153.com 证书续期 + 海报服务重启（每日计划任务调用）
$ErrorActionPreference = 'Continue'
$log = 'C:\Users\nainaijia\projects\tianluo-girl\poster\renew.log'
function Log($m) { Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) }

$env:PATH = "C:\Users\nainaijia\.acme.sh\bin;" + $env:PATH
$env:LE_WORKING_DIR = 'C:\Users\nainaijia\.acme.sh'
$cer = 'C:\Users\nainaijia\.acme.sh\pt2153.com_ecc\fullchain.cer'

Log '--- renew run start ---'
# 1) 续期（未到窗口时 acme.sh 会跳过，正常）
& bash -lc "C:/Users/nainaijia/.acme.sh/acme.sh --renew -d pt2153.com --dns dns_ali" 2>&1 | ForEach-Object { Log $_ }

# 2) 证书若在 10 分钟内更新过 -> 重启海报服务
if (((Get-Date) - (Get-Item $cer).LastWriteTime) -lt (New-TimeSpan -Minutes 10)) {
    # 按端口找旧进程（命令行是相对路径 server.py，不能按 'poster' 关键字过滤）
    Get-NetTCPConnection -LocalPort 8137 -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique |
      ForEach-Object { Stop-Process -Id $_ -Force; Log ("killed pid " + $_) }
    Start-Sleep -Seconds 1
    Start-Process -WindowStyle Hidden 'C:\Users\nainaijia\AppData\Local\Programs\Python\Python312\python.exe' `
      -ArgumentList '-u','server.py' -WorkingDirectory 'C:\Users\nainaijia\projects\tianluo-girl\poster'
    Log 'poster service restarted with new cert'
} else {
    Log 'cert not due, nothing to do'
}
Log '--- renew run end ---'
