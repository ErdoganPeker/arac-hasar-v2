# run_training.ps1
# Tek tiklamali, bulletproof egitim wrapper'i
# Kullanim:  powershell -ExecutionPolicy Bypass -File run_training.ps1
#   veya:    sag tik > "Run with PowerShell"
#
# Garantiler:
#   - Tum uyku/sleep/ekran kapanmalarini engeller (try/finally ile geri alinir)
#   - Lid close = ignore, CPU min %100, PCIe ASPM kapali
#   - GPU/disk/venv pre-flight
#   - Her run'da log: logs\train_<TS>.log (UTF-8)
#   - OOM yakalanirsa batch=2->1 fallback (yolo11m-seg @ 1024 icin)
#   - Cokerse otomatik resume (--resume_latest)
#   - Defender exclusion (training klasorlerine real-time scan kapali)
#   - Windows Update gec birakilmaz (servisleri durdurur)

[CmdletBinding()]
param(
    [string]$DamageModel  = "yolo11m-seg",
    [string]$PartsModel   = "yolo11s-seg",
    [int]   $DamageEpochs = 120,
    [int]   $PartsEpochs  = 80,
    [int]   $SeverityEpochs = 15,
    [int]   $ImgSz        = 1024,
    [int]   $InitBatch    = 2,        # yolo11m@1024 icin GUVENLI baslangic
    [int]   $Nbs          = 24,       # gradient accumulation hedefi
    [int]   $Patience     = 40,
    [int]   $SavePeriod   = 5,
    [string]$Cache        = "ram",
    [string]$CacheParts   = "disk"    # CarParts buyuk, RAM riski
)

$ErrorActionPreference = "Stop"
$projectRoot = "C:\Users\Erdogan\Desktop\arac-hasar-v2"
$mlDir       = Join-Path $projectRoot "services\ml"
$venvPython  = Join-Path $mlDir ".venv\Scripts\python.exe"
$logsDir     = Join-Path $mlDir "logs"
$ts          = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile     = Join-Path $logsDir "train_$ts.log"

if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[$([DateTime]::Now.ToString('HH:mm:ss'))] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

function Save-PowerSettings {
    # Mevcut timeout'lari sakla (try/finally'de geri yazilacak)
    $orig = @{
        Standby   = (& powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "AC Power Setting" | Out-String)
        Monitor   = (& powercfg /q SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Select-String "AC Power Setting" | Out-String)
    }
    return $orig
}

function Set-PowerForTraining {
    Write-Log "Power mgmt ayarlaniyor..."
    # Timeout'lari sifirla
    powercfg /change standby-timeout-ac 0    | Out-Null
    powercfg /change monitor-timeout-ac 0    | Out-Null
    powercfg /change disk-timeout-ac 0       | Out-Null
    powercfg /change hibernate-timeout-ac 0  | Out-Null

    # Lid close = ignore (kapagi kapansa bile devam etsin)
    powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0 2>$null | Out-Null

    # CPU min/max %100
    powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMIN 100 2>$null | Out-Null
    powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 100 2>$null | Out-Null

    # PCIe ASPM kapat (GPU bandwidth)
    powercfg /setacvalueindex SCHEME_CURRENT SUB_PCIEXPRESS ASPM 0 2>$null | Out-Null

    # High Performance plan (8c5e7fda... = High performance GUID)
    powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c 2>$null | Out-Null
    # Eger yoksa SCHEME_CURRENT'i tekrar aktif et
    powercfg /setactive SCHEME_CURRENT 2>$null | Out-Null

    # Presentation mode = ekran/sleep tamamen bastirilir
    Start-Process presentationsettings -ArgumentList "/start" -NoNewWindow -ErrorAction SilentlyContinue
    Write-Log "Power mgmt aktif: standby=0, monitor=0, lid=ignore, CPU=100, ASPM=off"
}

function Restore-PowerSettings {
    Write-Log "Power mgmt geri aliniyor..." "INFO"
    Stop-Process -Name "PresentationSettings" -Force -ErrorAction SilentlyContinue
    powercfg /change standby-timeout-ac 30   | Out-Null
    powercfg /change monitor-timeout-ac 15   | Out-Null
    powercfg /change disk-timeout-ac 20      | Out-Null
    powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 1 2>$null | Out-Null
    powercfg /setactive SCHEME_CURRENT 2>$null | Out-Null
    Write-Log "Power mgmt restore edildi (standby=30dk, monitor=15dk, lid=sleep)"
}

function Add-DefenderExclusions {
    Write-Log "Defender exclusion ekleniyor..."
    try {
        Add-MpPreference -ExclusionPath $projectRoot -ErrorAction Stop
        Add-MpPreference -ExclusionProcess "python.exe" -ErrorAction Stop
        Write-Log "Defender exclusion: $projectRoot + python.exe"
    } catch {
        Write-Log "Defender exclusion eklenemedi (admin lazim olabilir): $_" "WARN"
    }
}

function Pause-WindowsUpdates {
    Write-Log "Windows Update servisleri durduruluyor..."
    foreach ($svc in @("wuauserv", "UsoSvc", "WaaSMedicSvc")) {
        try {
            Stop-Service -Name $svc -Force -ErrorAction Stop
            Write-Log "  durduruldu: $svc"
        } catch {
            Write-Log "  durduralamadi (admin lazim?): $svc - $_" "WARN"
        }
    }
}

function Test-PreFlight {
    Write-Log "Pre-flight kontroller..."

    # 1. Python venv var mi
    if (-not (Test-Path $venvPython)) {
        Write-Log "venv Python bulunamadi: $venvPython" "FATAL"
        return $false
    }

    # 2. train_all.py var mi
    $trainScript = Join-Path $mlDir "train_all.py"
    if (-not (Test-Path $trainScript)) {
        Write-Log "train_all.py yok: $trainScript" "FATAL"
        return $false
    }

    # 3. nvidia-smi - GPU bos mu
    try {
        $smi = & nvidia-smi --query-gpu=memory.free,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>&1
        $parts = $smi -split ','
        $freeMb = [int]$parts[0].Trim()
        $usedMb = [int]$parts[1].Trim()
        $util   = [int]$parts[2].Trim()
        $temp   = [int]$parts[3].Trim()
        Write-Log "GPU: free=${freeMb}MB used=${usedMb}MB util=${util}% temp=${temp}C"
        if ($freeMb -lt 6500) {
            Write-Log "GPU yetersiz free VRAM ($freeMb MB). Diger sureci kapat." "FATAL"
            return $false
        }
        if ($temp -gt 70) {
            Write-Log "GPU baslangic sicakligi yuksek ($temp C). Soguma bekle." "WARN"
        }
    } catch {
        Write-Log "nvidia-smi hatasi: $_" "FATAL"
        return $false
    }

    # 4. Disk free
    $drive = Get-PSDrive C
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    Write-Log "Disk C: free=${freeGb} GB"
    if ($freeGb -lt 20) {
        Write-Log "Disk yetersiz: ${freeGb} GB. En az 20GB lazim." "FATAL"
        return $false
    }

    # 5. RAM
    $os = Get-CimInstance Win32_OperatingSystem
    $ramFreeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    Write-Log "RAM free: ${ramFreeGb} GB"
    if ($ramFreeGb -lt 8) {
        Write-Log "RAM dusuk ($ramFreeGb GB). Browser/IDE kapat." "WARN"
    }

    return $true
}

function Invoke-Training {
    param([int]$Batch, [bool]$Resume)

    $args = @(
        (Join-Path $mlDir "train_all.py"),
        "--full",
        "--damage_model", $DamageModel,
        "--parts_model", $PartsModel,
        "--damage_epochs", $DamageEpochs,
        "--parts_epochs", $PartsEpochs,
        "--severity_epochs", $SeverityEpochs,
        "--imgsz", $ImgSz,
        "--batch", $Batch,
        "--nbs", $Nbs,
        "--patience", $Patience,
        "--save_period", $SavePeriod,
        "--cache", $Cache,
        "--cache_parts", $CacheParts
    )
    if ($Resume) { $args += "--resume_latest" }

    Write-Log "Egitim BASLIYOR: batch=$Batch resume=$Resume"
    Write-Log "Komut: $venvPython $($args -join ' ')"
    Write-Log "----------------------------------------"

    # Tum stream'leri (stdout+stderr+verbose) merge et + log'a yaz
    & $venvPython @args *>&1 | Tee-Object -FilePath $logFile -Append
    return $LASTEXITCODE
}

function Test-OOMInLog {
    if (-not (Test-Path $logFile)) { return $false }
    $patterns = @(
        "out of memory",
        "CUDA out of memory",
        "OutOfMemoryError",
        "\[OOM\]"
    )
    foreach ($p in $patterns) {
        if (Select-String -Path $logFile -Pattern $p -Quiet -SimpleMatch:$false) {
            return $true
        }
    }
    return $false
}

# -------------------- MAIN --------------------

Write-Log "===================================================="
Write-Log "  arac-hasar-v2 train_all.py wrapper"
Write-Log "  Bundle root: $mlDir\runs\bundles\"
Write-Log "  Log: $logFile"
Write-Log "===================================================="

if (-not (Test-PreFlight)) {
    Write-Log "Pre-flight FAILED, cikis." "FATAL"
    exit 2
}

# Power management - try/finally ile garanti restore
Set-PowerForTraining
Add-DefenderExclusions
Pause-WindowsUpdates

$tStart = Get-Date
$exitCode = 1
$batches = @($InitBatch)
if ($InitBatch -ge 4) { $batches += 2 }
if ($InitBatch -ge 2) { $batches += 1 }

try {
    $resume = $false
    foreach ($b in $batches) {
        Write-Log "===> ATTEMPT batch=$b resume=$resume"
        $exitCode = Invoke-Training -Batch $b -Resume:$resume
        Write-Log "Exit code: $exitCode"

        if ($exitCode -eq 0) {
            Write-Log "BASARILI bitis." "SUCCESS"
            break
        }

        # OOM mu (exit 137 veya log'da pattern)?
        $isOom = ($exitCode -eq 137) -or (Test-OOMInLog)
        if ($isOom -and $b -ne $batches[-1]) {
            Write-Log "OOM tespit edildi. Batch dusurup retry..." "WARN"
            $resume = $true
            Start-Sleep -Seconds 10
            continue
        }
        # Diger hata: bir kez resume dene (orneksel cokme)
        if (-not $resume -and $exitCode -ne 130) {
            Write-Log "Beklenmeyen cokme. Resume ile retry..." "WARN"
            $resume = $true
            Start-Sleep -Seconds 10
            continue
        }
        Write-Log "Tum denemeler basarisiz." "FATAL"
        break
    }
} finally {
    $dt = (New-TimeSpan -Start $tStart).ToString()
    Write-Log "Toplam sure: $dt"
    Restore-PowerSettings
    Write-Log "Log dosyasi: $logFile"
}

# Bundle bilgisi
$lastBundle = Get-ChildItem (Join-Path $mlDir "runs\bundles") -Directory `
    -Filter "full_*" -ErrorAction SilentlyContinue `
    | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($lastBundle) {
    Write-Log "En son bundle: $($lastBundle.FullName)"
    $manifest = Join-Path $lastBundle.FullName "manifest.json"
    if (Test-Path $manifest) {
        Write-Log "Manifest: $manifest"
        Write-Log "Smoke overlay: $(Join-Path $lastBundle.FullName 'smoke_inference.jpg')"
    }
}

exit $exitCode
