"""
download_severity_roboflow.py — Roboflow Universe'ten araç hasar şiddeti dataset'i indir

Aday slug'lar arasında geçerli olan ilkini bulup indirir.
Hedef: ~1000-2500 görüntü, 3-sınıflı (hafif/orta/ağır benzeri) severity.

Çıktı: services/ml/data/severity_roboflow/
"""
import os
import sys
from pathlib import Path

API_KEY = os.environ.get("ROBOFLOW_API_KEY", "")
if not API_KEY:
    env_path = Path(__file__).parent.parent / "services" / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ROBOFLOW_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break
if not API_KEY:
    print("HATA: ROBOFLOW_API_KEY yok")
    sys.exit(1)

# Aday workspace/project/version slug'ları (bilinen severity datasetleri)
CANDIDATES = [
    # (workspace, project, version, format)
    ("car-damage-severity-detection", "car-damage-severity-detection", 1, "folder"),
    ("car-damage-severity", "car-damage-severity-dataset", 1, "folder"),
    ("damage-detection-tn50p", "car-damage-severity", 1, "folder"),
    ("cardd-severity", "car-damage-cardd-severity", 1, "folder"),
    ("car-damage-clf", "car-damage-severity", 1, "folder"),
    ("auto-damage", "car-damage-severity-3", 1, "folder"),
    ("car-classification", "car-damage-severity-cardd", 1, "folder"),
    ("damages", "car-damage-severity-classification", 1, "folder"),
    ("vehicle-damage", "severity-3-class", 1, "folder"),
    ("car-damage", "damage-severity-classification", 1, "folder"),
]

OUTPUT_DIR = Path(__file__).parent.parent / "services" / "ml" / "data" / "severity_roboflow"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(OUTPUT_DIR)

from roboflow import Roboflow
rf = Roboflow(api_key=API_KEY)
print(f">> Roboflow OK, {len(CANDIDATES)} aday denenecek\n")

found = None
for i, (ws, proj, ver, fmt) in enumerate(CANDIDATES, 1):
    print(f"[{i}/{len(CANDIDATES)}] {ws}/{proj} v{ver}...", end=" ", flush=True)
    try:
        workspace = rf.workspace(ws)
        project = workspace.project(proj)
        version = project.version(ver)
        n_imgs = version.images if hasattr(version, "images") else "?"
        print(f"[OK] FOUND ({n_imgs} images, type={project.type})")
        print(f"   classes: {project.classes}")
        found = (ws, proj, ver, fmt, project, version)
        break
    except Exception as e:
        err = str(e)[:120]
        print(f"[X] {err}")

if not found:
    print("\nHATA: Hiçbir aday slug geçerli değil. Manuel URL gerekli.")
    print("Lütfen Firefox'tan Roboflow Universe'de bir 3-class severity dataset URL'i paylaş.")
    sys.exit(2)

ws, proj, ver, fmt, project, version = found
print(f"\n>> Indiriliyor: {ws}/{proj} v{ver}, format={fmt}")
try:
    dataset = version.download(fmt)
    print(f">> İndirildi: {dataset.location}")
except Exception as e:
    print(f"İndirme hatası: {e}")
    sys.exit(3)
