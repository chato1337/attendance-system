# Registra el agente para que arranque con Windows.
# El binario es un proceso de consola: se usa una tarea programada, no el Administrador de servicios.
param(
    [string]$Binary = "C:\Program Files\Attendance\agent.exe",
    [string]$Config = "C:\ProgramData\Attendance\agent.yaml"
)

$taskName = "AttendanceEdgeAgent"
$action = New-ScheduledTaskAction -Execute $Binary -Argument "-config `"$Config`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "Tarea $taskName registrada. El gateway externo, si se usa, debe arrancar antes y escuchar solo en 127.0.0.1."
