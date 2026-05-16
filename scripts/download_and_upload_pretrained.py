"""
Roboflow Universe modellerini indir + HuggingFace Hub'a yukle.

Hedef HF repo: erdoganpeker/hasari-models (var olan custom modeller repo'su)
Subdir: pretrained/<id>/weights/best.pt

Cikti dizini (lokal):
    C:/Users/Erdogan/Desktop/arac-hasar-v2/services/backend/pretrained/<id>/weights/best.pt

Kullanim:
    python download_and_upload_pretrained.py [--skip-download] [--skip-upload]
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
BACKEND_PRETRAINED = ROOT / "services" / "backend" / "pretrained"
BACKEND_PRETRAINED.mkdir(parents=True, exist_ok=True)

# Roboflow API key
API_KEY = os.environ.get("ROBOFLOW_API_KEY", "")
if not API_KEY:
    env_path = ROOT / "services" / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("ROBOFLOW_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break
if not API_KEY:
    print("HATA: ROBOFLOW_API_KEY yok")
    sys.exit(1)

# HF token — sadece env'den oku, sabit token koyma
HF_TOKEN = os.environ.get("HF_TOKEN") or os.environ.get("HF_HUB_TOKEN")
if not HF_TOKEN:
    print("HATA: HF_TOKEN env yok (huggingface_hub upload icin gerekli)")
    sys.exit(1)

HF_REPO = "erdoganpeker/hasari-models"

# Indirilecek 3 Roboflow modeli
MODELS = [
    {
        "id": "roboflow_cardd_scratch_dent",
        "workspace": "carpro",
        "project": "car-scratch-and-dent",
        "version": 3,
        "format": "yolov8",
    },
    {
        "id": "roboflow_car_parts_seg",
        "workspace": "popular-benchmarks",
        "project": "car-parts-segmentation",
        "version": 2,
        "format": "yolov8",
    },
    {
        "id": "roboflow_cardd_severity",
        "workspace": "sreevishnu-damarla",
        "project": "car-damage-severity-mr5kk",
        "version": 1,
        "format": "yolov8",
    },
]


def download_roboflow_model(spec: dict) -> Path | None:
    """Tek bir Roboflow model'i indir. Return: best.pt yolu veya None."""
    from roboflow import Roboflow

    mid = spec["id"]
    target_dir = BACKEND_PRETRAINED / mid / "weights"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_pt = target_dir / "best.pt"

    if target_pt.exists() and target_pt.stat().st_size > 1_000_000:
        print(f"  [{mid}] zaten var ({target_pt.stat().st_size/1e6:.1f} MB), atla")
        return target_pt

    print(f"  [{mid}] Roboflow'tan iniyor: {spec['workspace']}/{spec['project']} v{spec['version']}")

    try:
        rf = Roboflow(api_key=API_KEY)
        project = rf.workspace(spec["workspace"]).project(spec["project"])
        version = project.version(spec["version"])

        # Hosted model.weights URL'i dene
        # Roboflow Universe'de bazı modeller pt indirilebilir.
        try:
            model = version.model  # type: ignore[attr-defined]
            if model is None:
                print(f"  [{mid}] HATA: version.model None — Roboflow Universe'de hosted weights yok")
                return None
            # Bazı versiyonlarda model.weights URL'si vardır:
            weights_url = getattr(model, "weights_url", None) or getattr(model, "weight_path", None)
            print(f"  [{mid}] model object: {type(model).__name__}, weights_url={weights_url}")
        except Exception as e:
            print(f"  [{mid}] version.model HATA: {e}")

        # Dene: version.deploy() ile pt link
        # En garantili: dataset indir (training data), sonra Roboflow'tan model id ile inference yap
        # Ama biz pt istiyoruz — eger Roboflow universe paylasmasi acaba universe.download dene
        try:
            # YOLO format download — dataset + bazı durumlarda hosted weights icerir
            dataset_dir = target_dir.parent
            dataset = version.download(spec["format"], location=str(dataset_dir / "_dataset"))
            ds_path = Path(dataset.location)
            print(f"  [{mid}] dataset indi: {ds_path}")

            # Dataset icinde best.pt aranabilir
            for pt_candidate in ds_path.rglob("*.pt"):
                if pt_candidate.stat().st_size > 1_000_000:
                    print(f"  [{mid}] pt bulundu: {pt_candidate}")
                    shutil.copy(pt_candidate, target_pt)
                    return target_pt
            print(f"  [{mid}] dataset icinde .pt yok — Roboflow publisher weights paylasmamis")
            return None
        except Exception as e:
            print(f"  [{mid}] dataset HATA: {e}")
            return None

    except Exception as exc:
        print(f"  [{mid}] FATAL: {exc}")
        return None


def upload_to_hf_hub(local_files: list[tuple[str, Path]]):
    """HF Hub'a pretrained/<id>/weights/best.pt olarak yukle."""
    from huggingface_hub import HfApi

    api = HfApi(token=HF_TOKEN)
    print(f"\n>> HF Hub upload to {HF_REPO}")

    for mid, pt_path in local_files:
        if not pt_path or not pt_path.exists():
            print(f"  [{mid}] SKIP — pt yok")
            continue
        size_mb = pt_path.stat().st_size / 1e6
        target_in_repo = f"pretrained/{mid}/weights/best.pt"
        print(f"  [{mid}] uploading {size_mb:.1f} MB -> {HF_REPO}:{target_in_repo}")
        api.upload_file(
            path_or_fileobj=str(pt_path),
            path_in_repo=target_in_repo,
            repo_id=HF_REPO,
            repo_type="model",
            commit_message=f"add pretrained {mid}",
        )
        print(f"  [{mid}] OK")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    downloaded = []
    if not args.skip_download:
        print(">> Roboflow modelleri iniyor...")
        for spec in MODELS:
            pt = download_roboflow_model(spec)
            downloaded.append((spec["id"], pt))
            time.sleep(2)  # rate limit
    else:
        for spec in MODELS:
            pt = BACKEND_PRETRAINED / spec["id"] / "weights" / "best.pt"
            downloaded.append((spec["id"], pt if pt.exists() else None))

    print("\n>> Indirme sonuclari:")
    for mid, pt in downloaded:
        status = "OK" if pt and pt.exists() else "FAIL"
        print(f"  {mid}: {status}")

    if not args.skip_upload:
        upload_to_hf_hub(downloaded)

    print("\n>> Bitti.")


if __name__ == "__main__":
    main()
