# setup.ps1 — Araç hasar tespiti ML ortamı kurulumu (Windows PowerShell)
# Kullanım: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Araç Hasar Tespiti — ML Ortam Kurulumu (Windows) ===" -ForegroundColor Cyan
Write-Host ""

# ---------------- GPU & CUDA tespiti ----------------
$gpuName = ""
$computeCap = ""
$useBlackwell = $false

if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpuLine = (& nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader 2>&1 | Select-Object -First 1)
    if ($gpuLine) {
        $parts = $gpuLine -split ","
        $gpuName = $parts[0].Trim()
        $computeCap = $parts[1].Trim()
        Write-Host "Tespit edilen GPU: $gpuName"
        Write-Host "Compute capability: $computeCap"
        if ($computeCap -match "^1[23]\.") {
            $useBlackwell = $true
            Write-Host ">> Blackwell mimarisi tespit edildi. cu128 wheels gerekli." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "UYARI: nvidia-smi bulunamadı. CPU-only kurulum yapılacak." -ForegroundColor Yellow
}

# ---------------- Klasör yapısı ----------------
Write-Host ""
Write-Host "[1/6] Klasör yapısı..." -ForegroundColor Cyan
$dirs = @(
    "data\CarDD_release",
    "data\cardd_yolo\images\train", "data\cardd_yolo\images\val", "data\cardd_yolo\images\test",
    "data\cardd_yolo\labels\train", "data\cardd_yolo\labels\val", "data\cardd_yolo\labels\test",
    "data\parts_yolo", "data\severity_roboflow", "data\cardd_hf", "data\raw",
    "runs", "weights", "notebooks", "logs"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

# ---------------- Python ortamı ----------------
Write-Host ""
Write-Host "[2/6] Python ortamı..." -ForegroundColor Cyan

$useConda = $false
if (Get-Command conda -ErrorAction SilentlyContinue) {
    $envs = conda env list 2>&1
    if (-not ($envs -match "^hasar\s")) {
        Write-Host "Conda env 'hasar' oluşturuluyor..."
        conda create -n hasar python=3.11 -y
    }
    Write-Host "Conda env 'hasar' aktive edilecek."
    # PowerShell'de conda aktivasyonu için conda init powershell gerekli (kullanıcı kendisi yapacak)
    Write-Host "ÖNEMLİ: Yeni PowerShell penceresinde 'conda activate hasar' çalıştır, sonra bu script'i tekrar koş." -ForegroundColor Yellow
    $useConda = $true
} else {
    if (-not (Test-Path ".venv")) {
        Write-Host "venv oluşturuluyor..."
        python -m venv .venv
    }
    & .\.venv\Scripts\Activate.ps1
    Write-Host "venv aktif: .venv"
}

# ---------------- pip ----------------
Write-Host ""
Write-Host "[3/6] pip güncelleniyor..." -ForegroundColor Cyan
python -m pip install --upgrade pip setuptools wheel

# ---------------- PyTorch ----------------
Write-Host ""
Write-Host "[4/6] PyTorch kuruluyor..." -ForegroundColor Cyan
if ($useBlackwell) {
    Write-Host "  -> Blackwell için PyTorch cu128"
    try {
        python -m pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    } catch {
        Write-Host "  -> cu128 stable bulunamadı, nightly deneniyor..." -ForegroundColor Yellow
        python -m pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128
    }
} elseif ($gpuName) {
    Write-Host "  -> Pre-Blackwell NVIDIA için PyTorch cu121"
    python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
} else {
    Write-Host "  -> CPU-only PyTorch"
    python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
}

# ---------------- ML kütüphaneleri ----------------
Write-Host ""
Write-Host "[5/6] ML kütüphaneleri..." -ForegroundColor Cyan
python -m pip install `
    "ultralytics>=8.3.40" `
    "pycocotools-windows" `
    "fiftyone" `
    "wandb" `
    "matplotlib" `
    "seaborn" `
    "pandas" `
    "pillow" `
    "opencv-python" `
    "tqdm" `
    "pyyaml" `
    "huggingface_hub" `
    "datasets" `
    "roboflow"

# ---------------- CUDA doğrulama ----------------
Write-Host ""
Write-Host "[6/6] CUDA / GPU doğrulama..." -ForegroundColor Cyan
$verifyScript = @'
import sys
try:
    import torch
except ImportError:
    print("PyTorch yüklü değil.")
    sys.exit(1)

print(f"PyTorch: {torch.__version__}")
print(f"CUDA mevcut: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    props = torch.cuda.get_device_properties(0)
    print(f"GPU: {props.name}")
    print(f"VRAM: {props.total_memory / 1e9:.1f} GB")
    print(f"Compute capability: sm_{props.major}{props.minor}")
    try:
        x = torch.randn(64, 64, device='cuda')
        y = x @ x.T
        torch.cuda.synchronize()
        print("CUDA tensor smoke test: OK")
    except RuntimeError as e:
        print(f"CUDA TEST HATASI: {e}")
        print("Bu GPU icin PyTorch derlemesi uyumsuz olabilir (Blackwell -> cu128 gerekli).")
        sys.exit(2)
else:
    print("UYARI: CUDA yok. Egitim CPU uzerinde cok yavas olacak.")
'@
$tmp = New-TemporaryFile
Set-Content -Path $tmp -Value $verifyScript -Encoding utf8
python $tmp
Remove-Item $tmp -Force

# ---------------- Pretrained pre-fetch ----------------
Write-Host ""
Write-Host "[Opsiyonel] Pretrained YOLO ağırlıkları pre-fetch..." -ForegroundColor Cyan
$prefetch = @'
from ultralytics import YOLO
for w in ["yolo11n-seg.pt", "yolo11s-seg.pt", "yolo11m-seg.pt"]:
    try:
        YOLO(w)
        print(f"  + {w}")
    except Exception as e:
        print(f"  - {w}: {e}")
'@
$tmp = New-TemporaryFile
Set-Content -Path $tmp -Value $prefetch -Encoding utf8
try { python $tmp } catch { Write-Host "Atlandı." }
Remove-Item $tmp -Force

Write-Host ""
Write-Host "=== Kurulum tamamlandı ===" -ForegroundColor Green
Write-Host ""
Write-Host "Sonraki adımlar:" -ForegroundColor Cyan
Write-Host "  1. CarDD veri setini indir:"
Write-Host "     HuggingFace mirror: python ..\..\scripts\download_data.py --cardd-hf"
Write-Host "     Veya resmi form: https://cardd-ustc.github.io"
Write-Host "  2. Parça verisi: python prepare_parts_data.py --use_ultralytics"
Write-Host "  3. Şiddet verisi: `$env:ROBOFLOW_API_KEY = '...' ; python ..\..\scripts\download_data.py --roboflow-severity"
Write-Host "  4. Baseline eğitim (RTX 5050 8GB için):"
Write-Host "     python train.py --model yolo11s-seg --epochs 100 --batch 16 --imgsz 640"
