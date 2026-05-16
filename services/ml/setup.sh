#!/bin/bash
# setup.sh — Araç hasar tespiti ML ortamı kurulumu (Linux/macOS/WSL)
# Windows için: setup.ps1 kullan
#
# Kullanım: chmod +x setup.sh && ./setup.sh

set -e

echo "=== Araç Hasar Tespiti — ML Ortam Kurulumu ==="
echo ""

# ---------------- GPU & CUDA tespiti ----------------
GPU_NAME=""
COMPUTE_CAP=""
USE_BLACKWELL=0

if command -v nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)
    COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1)
    echo "Tespit edilen GPU: ${GPU_NAME}"
    echo "Compute capability: ${COMPUTE_CAP}"

    # Blackwell mimarisi sm_120+ (RTX 50 serisi, B100 vs.)
    if [[ "${COMPUTE_CAP}" == "12."* ]] || [[ "${COMPUTE_CAP}" == "13."* ]]; then
        USE_BLACKWELL=1
        echo ">> Blackwell mimarisi tespit edildi (sm_${COMPUTE_CAP//./}). cu128 wheels gerekli."
    fi
else
    echo "UYARI: nvidia-smi bulunamadı. CPU-only kurulum yapılacak (eğitim çok yavaş)."
fi

# ---------------- Klasör yapısı ----------------
echo ""
echo "[1/6] Klasör yapısı oluşturuluyor..."
mkdir -p data/CarDD_release
mkdir -p data/cardd_yolo/{images,labels}/{train,val,test}
mkdir -p data/parts_yolo data/severity_roboflow data/cardd_hf data/raw
mkdir -p runs weights notebooks logs

# ---------------- Python ortamı ----------------
echo ""
echo "[2/6] Python ortamı hazırlanıyor..."
if command -v conda &> /dev/null; then
    if ! conda env list | grep -q "^hasar "; then
        conda create -n hasar python=3.11 -y
    fi
    eval "$(conda shell.bash hook)"
    conda activate hasar
    echo "Conda env: hasar aktif."
else
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    echo "venv: .venv aktif."
fi

# ---------------- pip + temel paketler ----------------
echo ""
echo "[3/6] pip güncelleniyor..."
pip install --upgrade pip setuptools wheel

echo ""
echo "[4/6] PyTorch kuruluyor..."
if [ "${USE_BLACKWELL}" -eq 1 ]; then
    # Blackwell (sm_120) — CUDA 12.8 wheels gerekli (PyTorch 2.6+)
    # Stable 2.6 cu128 mevcut; nightly fallback için yorum bırakıyoruz.
    echo "  → Blackwell için PyTorch 2.6+ cu128"
    pip install --pre torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu128 || {
        echo "  → cu128 stable bulunamadı, nightly deneniyor..."
        pip install --pre torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/nightly/cu128
    }
elif [ -n "${GPU_NAME}" ]; then
    # Eski NVIDIA (Ampere, Ada, Hopper) — cu121 yeterli
    echo "  → Pre-Blackwell NVIDIA için PyTorch cu121"
    pip install torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu121
else
    # CPU-only
    echo "  → CPU-only PyTorch"
    pip install torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu
fi

echo ""
echo "[5/6] ML kütüphaneleri kuruluyor..."
pip install \
    "ultralytics>=8.3.40" \
    "pycocotools" \
    "fiftyone" \
    "wandb" \
    "matplotlib" \
    "seaborn" \
    "pandas" \
    "pillow" \
    "opencv-python" \
    "tqdm" \
    "pyyaml" \
    "huggingface_hub" \
    "datasets" \
    "roboflow"

# ---------------- CUDA doğrulama ----------------
echo ""
echo "[6/6] CUDA / GPU doğrulama..."
python - <<'PY'
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
    # Quick smoke test — Blackwell uyumsuzluğunu erken yakala
    try:
        x = torch.randn(64, 64, device='cuda')
        y = x @ x.T
        torch.cuda.synchronize()
        print("CUDA tensor smoke test: OK")
    except RuntimeError as e:
        print(f"CUDA TEST HATASI: {e}")
        print("Bu GPU için PyTorch derlemesi uyumsuz olabilir (Blackwell → cu128 gerekli).")
        sys.exit(2)
else:
    print("UYARI: CUDA yok. Eğitim CPU üzerinde çok yavaş olacak.")
PY

# ---------------- Pretrained weights pre-fetch ----------------
echo ""
echo "[Opsiyonel] Pretrained YOLO ağırlıkları pre-fetch ediliyor (Ctrl+C ile atla)..."
python - <<'PY' || echo "Atlandı."
from ultralytics import YOLO
for w in ["yolo11n-seg.pt", "yolo11s-seg.pt", "yolo11m-seg.pt"]:
    try:
        YOLO(w)
        print(f"  ✓ {w}")
    except Exception as e:
        print(f"  ✗ {w}: {e}")
PY

cat <<EOF

=== Kurulum tamamlandı ===

Sonraki adımlar:
  1. CarDD veri setini indir:
     - HuggingFace mirror (önerilen, anında):
         python ../../scripts/download_data.py --cardd-hf
     - Veya resmi form (CarDD lisans): https://cardd-ustc.github.io
  2. Parça verisi (Ultralytics otomatik):
         python prepare_parts_data.py --use_ultralytics
  3. Şiddet verisi (Roboflow):
         export ROBOFLOW_API_KEY=...
         python ../../scripts/download_data.py --roboflow-severity
  4. Baseline eğitim (RTX 5050 8GB için önerilen):
         python train.py --model yolo11s-seg --epochs 100 --batch 16 --imgsz 640

Conda kullandıysan unutma: conda activate hasar
EOF
