<#
.SYNOPSIS
    Programma le sessioni di quiz patente obbligatorie in Windows Task Scheduler.
    Ogni sessione = 30 domande casuali in modalità --forzato (vanno completate
    tutte, poi la finestra si chiude da sola dopo 8 secondi). Non blocca il PC.

    Orari e giorni si leggono da pianificazione.json (nella stessa cartella):
        "attivo":  true = crea le task, false = le rimuove
        "orari":   elenco di orari HH:mm
        "weekend": true = anche sabato e domenica

    Il modo più semplice è da terminale WSL:
        patente --pianifica          applica pianificazione.json
        patente --pianifica stato    mostra le task configurate
        patente --pianifica rimuovi  rimuove tutte le task

.PARAMETER QuizDir
    Cartella WSL (percorso Linux) in cui si trova patente.py.
    Default: ~/patente

.PARAMETER Times
    Elenco di orari HH:mm. Se indicato, sostituisce "orari" di pianificazione.json.

.PARAMETER AllDays
    Se presente, programma anche il weekend (sostituisce "weekend" del file).

.PARAMETER Status
    Mostra lo stato delle scheduled task QuizPatente già configurate.

.PARAMETER Uninstall
    Rimuove tutte le scheduled task QuizPatente.

.EXAMPLE
    .\setup_quiz_scheduler.ps1
    .\setup_quiz_scheduler.ps1 -QuizDir "~/dev/patente" -Times "10:30","15:00"
    .\setup_quiz_scheduler.ps1 -Status
    .\setup_quiz_scheduler.ps1 -Uninstall

.NOTES
    Se PowerShell rifiuta per execution policy, lancia così:
        powershell -ExecutionPolicy Bypass -File .\setup_quiz_scheduler.ps1
    Non serve avviare come amministratore: le task sono registrate solo per il tuo utente.
#>
param(
    [string]$QuizDir = "~/patente",
    [string[]]$Times,
    [switch]$AllDays,
    [switch]$Status,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
# accenti leggibili anche quando lo script è lanciato dal terminale WSL
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$TaskPrefix = "QuizPatente_"
$TaskFolder = "\QuizPatente"
$ConfigFile = Join-Path $PSScriptRoot "pianificazione.json"

function Get-QuizTasks {
    Get-ScheduledTask -TaskPath "$TaskFolder\" -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -like "$TaskPrefix*" }
}

function Remove-QuizTasks {
    foreach ($t in Get-QuizTasks) {
        Write-Host "  rimuovo $($t.TaskName)"
        Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false
    }
}

# ---- configurazione ---------------------------------------------------------
# Valori di default, poi pianificazione.json, poi i parametri da riga di comando.
$active = $true
$weekend = $false
$configTimes = @("11:00", "14:30", "16:00")
if (Test-Path $ConfigFile) {
    $config = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -ne $config.attivo)  { $active = [bool]$config.attivo }
    if ($null -ne $config.weekend) { $weekend = [bool]$config.weekend }
    if ($config.orari)             { $configTimes = @($config.orari) }
}
if ($Times)   { $configTimes = $Times }
if ($AllDays) { $weekend = $true }
$Times = $configTimes

foreach ($t in $Times) {
    if ($t -notmatch '^([01]\d|2[0-3]):[0-5]\d$') {
        Write-Warning "Orario non valido: '$t' (formato HH:mm, es. 09:30)"
        exit 1
    }
}

# ---- -Status ----------------------------------------------------------------
if ($Status) {
    $tasks = Get-QuizTasks
    if (-not $tasks) {
        Write-Host "Nessuna scheduled task QuizPatente configurata."
        exit 0
    }
    foreach ($t in $tasks) {
        $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -TaskPath $t.TaskPath
        $trig = ($t.Triggers | ForEach-Object { $_.StartBoundary } | Select-Object -First 1)
        $hhmm = if ($trig) { ([datetime]$trig).ToString("HH:mm") } else { "?" }
        Write-Host ("  {0,-28}  orario {1}  stato {2}  prossima {3}" -f `
            $t.TaskName, $hhmm, $t.State, $info.NextRunTime)
    }
    exit 0
}

# ---- -Uninstall (o "attivo": false nel file) --------------------------------
if ($Uninstall -or -not $active) {
    if (-not $Uninstall) { Write-Host "pianificazione.json ha ""attivo"": false" }
    if (-not (Get-QuizTasks)) {
        Write-Host "Nessuna scheduled task QuizPatente da rimuovere."
    } else {
        Remove-QuizTasks
    }
    # Prova a rimuovere la cartella se vuota
    try {
        $svc = New-Object -ComObject Schedule.Service
        $svc.Connect()
        $root = $svc.GetFolder("\")
        $root.DeleteFolder("QuizPatente", 0)
    } catch {}
    Write-Host "Fatto."
    exit 0
}

# ---- Install ----------------------------------------------------------------
Write-Host "Verifico WSL..." -NoNewline
$null = & wsl.exe echo ok 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host " errore."
    Write-Warning "WSL non raggiungibile. Verifica che WSL sia installato e funzionante."
    exit 1
}
Write-Host " ok."

Write-Host "Verifico python3 in WSL..." -NoNewline
$null = & wsl.exe bash -lc "command -v python3" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host " assente."
    Write-Warning "python3 non trovato in WSL. Installalo con:  sudo apt install python3"
    exit 1
}
Write-Host " ok."

Write-Host "Verifico $QuizDir/patente.py in WSL..." -NoNewline
$res = (& wsl.exe bash -lc "test -f $QuizDir/patente.py && test -d $QuizDir/domande && test -d $QuizDir/quiz && echo OK" 2>&1).Trim()
if ($res -ne "OK") {
    Write-Host " non trovato."
    Write-Warning "patente.py o le cartelle domande/ e quiz/ non trovati in $QuizDir (dentro WSL)."
    Write-Host  "Serve tutto il progetto (patente.py + domande/ + quiz/), non solo patente.py."
    Write-Host  "Se hai la cartella su Windows, p.es. in Download, copiala così:"
    Write-Host  "  wsl bash -c 'cp -r /mnt/c/Users/$env:USERNAME/Downloads/patente ~/patente'"
    exit 1
}
Write-Host " ok."

$days = if ($weekend) {
    @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
} else {
    @("Monday","Tuesday","Wednesday","Thursday","Friday")
}

# Comando da far girare in WSL. L'eseguibile della scheduled task è cmd.exe,
# che apre una finestra console e poi lancia wsl.exe → bash → python3.
# cmd.exe /c chiude la finestra quando il quiz finisce (patente.py --forzato
# aspetta 8 secondi prima di uscire, così fai in tempo a leggere l'esito).
$bashCmd = "cd $QuizDir && python3 patente.py --forzato"
$cmdArgs = "/c wsl.exe bash -lc `"$bashCmd`""

# Tolgo tutte le task esistenti: così un orario rimosso dal file sparisce davvero
Write-Host ""
Remove-QuizTasks

foreach ($t in $Times) {
    $safeName = $t -replace ":", ""
    $taskName = "$TaskPrefix$safeName"

    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmdArgs
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $t
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)

    Register-ScheduledTask -TaskName $taskName -TaskPath $TaskFolder `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description "Quiz patente obbligatorio alle $t" | Out-Null

    Write-Host ("  creato: {0}  @ {1}  ({2})" -f $taskName, $t, ($days -join ","))
}

Write-Host ""
Write-Host "Fatto. Le finestre quiz si apriranno automaticamente a:"
Write-Host "  $($Times -join '   ')"
Write-Host ""
Write-Host "Per cambiare orari: modifica pianificazione.json, poi  patente --pianifica"
Write-Host "Puoi anche aprire 'Utilità di pianificazione' → cartella 'QuizPatente' per vederle."
