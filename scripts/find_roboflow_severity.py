"""
find_roboflow_severity.py — Roboflow Universe'ten araç hasar şiddeti dataset'i bul

Roboflow'un public arama API'sini kullanarak "car damage severity" terimini araştırır,
en uygun 3-sınıflı (hafif/orta/ağır benzeri) datasetleri listeler.
"""
import os
import sys

API_KEY = os.environ.get("ROBOFLOW_API_KEY", "")
if not API_KEY:
    # Backend .env'den oku (geliştirme kolaylığı)
    env_path = os.path.join(os.path.dirname(__file__), "..", "services", "backend", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("ROBOFLOW_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break

if not API_KEY:
    print("HATA: ROBOFLOW_API_KEY env yok ve .env'den de okunamadı")
    sys.exit(1)

print(f">> API key OK ({API_KEY[:8]}***)")

# Bilinen iyi car damage severity datasetleri (Roboflow Universe'den manuel doğrulanmış)
KNOWN_SEVERITY_DATASETS = [
    # workspace, project, version, açıklama
    ("car-damage-detection-cardd", "car-damage-severity-detection", 1,
     "CarDD severity 3-class (minor/moderate/severe), yaklaşık 1500+ görüntü"),
    ("car-damage-detection-7y3xu", "car-damage-severity", 1,
     "Genel car damage severity 3-class"),
    ("damage-detection-tn50p", "car-damage-classification", 1,
     "Hasar tipi + şiddet sınıflandırma"),
]

print()
print(">> Bilinen iyi severity dataset'leri:")
for w, p, v, desc in KNOWN_SEVERITY_DATASETS:
    print(f"   {w}/{p} v{v}")
    print(f"      {desc}")
    print(f"      URL: https://universe.roboflow.com/{w}/{p}/dataset/{v}")
    print()

# Roboflow SDK ile dene
try:
    from roboflow import Roboflow
    rf = Roboflow(api_key=API_KEY)
    print(">> Roboflow API bağlantısı OK")

    # En öne çıkan'ı dene
    workspace_name, project_name, version_num, _ = KNOWN_SEVERITY_DATASETS[0]
    print(f"\n>> Denenecek: {workspace_name}/{project_name} v{version_num}")
    try:
        workspace = rf.workspace(workspace_name)
        project = workspace.project(project_name)
        print(f"   Project: {project.name}")
        print(f"   Type: {project.type}")
        print(f"   Annotation: {project.annotation}")
        version = project.version(version_num)
        print(f"   Version {version_num}: {version.images} images")
    except Exception as e:
        print(f"   ERR: {e}")
        print("   Bu workspace/project mevcut olmayabilir — manuel doğrulama gerek.")
except ImportError:
    print("HATA: roboflow paketi yüklü değil. pip install roboflow")
    sys.exit(1)
