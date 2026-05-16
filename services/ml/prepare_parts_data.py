"""
prepare_parts_data.py
Parça segmentasyonu icin veri seti birlestirme/hazirlama.

Iki ana kaynak:
1. Ultralytics CarParts-Seg: Hazir, otomatik iner
2. Kullanici Roboflow Universe'den export ettigi setler

Kullanim:
    # Sadece Ultralytics seti ile baslat
    python prepare_parts_data.py --use_ultralytics --output_dir data/parts_yolo

    # Ek Roboflow setlerini de birlestir
    python prepare_parts_data.py --use_ultralytics \
        --extra_dirs data/roboflow_parts1 data/roboflow_parts2 \
        --output_dir data/parts_combined
"""
import argparse
import shutil
from collections import Counter
from pathlib import Path

import yaml
from tqdm import tqdm


# Standart parça sınıf listesi - Ultralytics CarParts-Seg ile uyumlu
# Bunu kendi ihtiyaclarina gore daralt/genislet
STANDARD_PARTS = [
    "back_bumper",
    "back_door",
    "back_glass",
    "back_left_door",
    "back_left_light",
    "back_light",
    "back_right_door",
    "back_right_light",
    "front_bumper",
    "front_glass",
    "front_left_door",
    "front_left_light",
    "front_light",
    "front_right_door",
    "front_right_light",
    "hood",
    "left_mirror",
    "right_mirror",
    "tailgate",
    "trunk",
    "wheel",
]


def download_ultralytics_carparts(output_dir):
    """Ultralytics CarParts-Seg veri setini indirir.

    Bu Ultralytics tarafindan otomatik yonetilir; ilk training'de iner.
    Burada manuel olarak tetikliyoruz.
    """
    print("Ultralytics CarParts-Seg indiriliyor...")
    # Ultralytics'in dataset yonetimi otomatik; bir dummy load ile tetikle
    try:
        from ultralytics.utils.downloads import safe_download
        from ultralytics.utils import SETTINGS
        datasets_dir = Path(SETTINGS["datasets_dir"])
        target = datasets_dir / "carparts-seg"
        if target.exists():
            print(f"Mevcut: {target}")
            return target

        # Ultralytics'in built-in mekanizmasini kullan
        from ultralytics.cfg import get_cfg
        from ultralytics import YOLO
        m = YOLO("yolo26n-seg.pt")
        # Bir dummy val tetiklemesiyle veriyi indir
        try:
            m.val(data="carparts-seg.yaml", batch=1, device="cpu", workers=0)
        except Exception:
            pass  # Sadece indirmek icin
        return target
    except Exception as e:
        print(f"UYARI: Otomatik indirme basarisiz: {e}")
        print("Manuel: https://docs.ultralytics.com/datasets/segment/carparts-seg/")
        return None


def normalize_class_name(name):
    """Sinif ismini standartlastir (lowercase, underscore)."""
    return name.lower().strip().replace(" ", "_").replace("-", "_")


def remap_labels(src_lbl_dir, dst_lbl_dir, src_classes, dst_classes):
    """Bir label klasorundeki sinif id'lerini hedef tabloya gore yeniden esle.

    Bilinmeyen siniflar dusurulur.
    """
    dst_lbl_dir.mkdir(parents=True, exist_ok=True)

    # src_idx -> dst_idx eslemesi
    mapping = {}
    for src_idx, src_name in enumerate(src_classes):
        norm = normalize_class_name(src_name)
        if norm in dst_classes:
            mapping[src_idx] = dst_classes.index(norm)

    if not mapping:
        print(f"UYARI: {src_lbl_dir} icin hicbir sinif eslenmedi")
        print(f"  Kaynak siniflar: {src_classes[:5]}...")
        return Counter()

    class_counter = Counter()
    for lbl_file in tqdm(list(src_lbl_dir.glob("*.txt")), desc=f"Remap {src_lbl_dir.name}"):
        new_lines = []
        with open(lbl_file, "r") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                src_cls = int(parts[0])
                if src_cls not in mapping:
                    continue
                dst_cls = mapping[src_cls]
                parts[0] = str(dst_cls)
                new_lines.append(" ".join(parts))
                class_counter[dst_classes[dst_cls]] += 1

        # Bos olsa bile yaz
        with open(dst_lbl_dir / lbl_file.name, "w") as f:
            f.write("\n".join(new_lines))

    return class_counter


def merge_dataset(src_dir, dst_dir, src_classes, dst_classes):
    """Bir YOLO formatli veri setini hedef klasor altina merge et."""
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)

    splits = ["train", "val", "test"]
    total_counter = Counter()

    for split in splits:
        src_img = src_dir / "images" / split
        src_lbl = src_dir / "labels" / split
        if not src_img.exists():
            continue

        dst_img = dst_dir / "images" / split
        dst_lbl = dst_dir / "labels" / split
        dst_img.mkdir(parents=True, exist_ok=True)

        # Goruntuleri kopyala (isim catismalarini onlemek icin prefix ekle)
        prefix = src_dir.name + "_"
        for img_path in src_img.glob("*"):
            if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            new_name = prefix + img_path.name
            shutil.copy2(img_path, dst_img / new_name)

            # Etiket dosyasini da kopyala (yeniden esleme ile)
            lbl_src = src_lbl / (img_path.stem + ".txt")
            if not lbl_src.exists():
                continue

            # Tek dosyayi remap et
            new_lines = []
            mapping = {i: dst_classes.index(normalize_class_name(c))
                       for i, c in enumerate(src_classes)
                       if normalize_class_name(c) in dst_classes}
            with open(lbl_src, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    src_cls = int(parts[0])
                    if src_cls not in mapping:
                        continue
                    dst_cls = mapping[src_cls]
                    parts[0] = str(dst_cls)
                    new_lines.append(" ".join(parts))
                    total_counter[dst_classes[dst_cls]] += 1

            with open(dst_lbl / (prefix + img_path.stem + ".txt"), "w") as f:
                f.write("\n".join(new_lines))

    return total_counter


def load_yaml_classes(yaml_path):
    """Bir YOLO yaml dosyasindan sinif listesini al."""
    with open(yaml_path, "r") as f:
        cfg = yaml.safe_load(f)
    names = cfg.get("names", {})
    if isinstance(names, dict):
        # 0..n-1 sirayla cek
        return [names[i] for i in sorted(names.keys())]
    return list(names)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--use_ultralytics", action="store_true",
                        help="Ultralytics CarParts-Seg'i indir ve dahil et")
    parser.add_argument("--extra_dirs", nargs="*", default=[],
                        help="Eklenecek Roboflow/diger setlerin yolu (her birinde data.yaml olmali)")
    parser.add_argument("--classes_file", type=str, default=None,
                        help="Ozel sinif listesi (her satirda bir sinif). Yoksa STANDARD_PARTS")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Hedef sinif listesini belirle
    if args.classes_file:
        with open(args.classes_file, "r") as f:
            dst_classes = [normalize_class_name(l) for l in f if l.strip()]
    else:
        dst_classes = [normalize_class_name(c) for c in STANDARD_PARTS]

    print(f"Hedef {len(dst_classes)} sinif:")
    for i, c in enumerate(dst_classes):
        print(f"  {i}: {c}")
    print()

    total_counter = Counter()

    # 1) Ultralytics seti
    if args.use_ultralytics:
        ultra_dir = download_ultralytics_carparts(out_dir)
        if ultra_dir and ultra_dir.exists():
            yaml_path = ultra_dir / "data.yaml"
            if not yaml_path.exists():
                yaml_path = ultra_dir.parent / "carparts-seg.yaml"
            if yaml_path.exists():
                src_classes = load_yaml_classes(yaml_path)
                print(f"\nUltralytics setinde {len(src_classes)} sinif var.")
                cnt = merge_dataset(ultra_dir, out_dir, src_classes, dst_classes)
                total_counter.update(cnt)
                print(f"  Eklenen: {dict(cnt)}")

    # 2) Ekstra setler
    for extra in args.extra_dirs:
        extra_path = Path(extra)
        yaml_path = extra_path / "data.yaml"
        if not yaml_path.exists():
            print(f"UYARI: {yaml_path} bulunamadi, atlandi.")
            continue
        src_classes = load_yaml_classes(yaml_path)
        print(f"\n{extra}: {len(src_classes)} sinif")
        cnt = merge_dataset(extra_path, out_dir, src_classes, dst_classes)
        total_counter.update(cnt)
        print(f"  Eklenen: {dict(cnt)}")

    # 3) parts.yaml yaz
    yaml_content = f"""# parts.yaml - Parca segmentasyonu konfigi
path: {out_dir.resolve()}
train: images/train
val: images/val
test: images/test

nc: {len(dst_classes)}

names:
"""
    for i, c in enumerate(dst_classes):
        yaml_content += f"  {i}: {c}\n"

    with open("parts.yaml", "w") as f:
        f.write(yaml_content)

    print(f"\n=== Tamamlandi ===")
    print(f"Cikti: {out_dir.resolve()}")
    print(f"Konfig: parts.yaml")
    print(f"Toplam etiket dagilimi:")
    for cls, cnt in total_counter.most_common():
        print(f"  {cls:25s} {cnt}")

    # Dengesizlik uyarisi
    if total_counter:
        max_cnt = max(total_counter.values())
        min_cnt = min(total_counter.values())
        if max_cnt > 10 * min_cnt:
            print(f"\nUYARI: Sinif dengesizligi yuksek ({max_cnt}:{min_cnt}).")
            print(f"  Egitimde class_weights ekle veya az ornekli siniflar icin veri topla.")


if __name__ == "__main__":
    main()
