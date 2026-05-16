"""
prepare_data.py
CarDD COCO formatindaki annotations'lari YOLO segmentation formatina cevirir.

Kullanim:
    python prepare_data.py \
        --cardd_root data/CarDD_release/CarDD_COCO \
        --output_dir data/cardd_yolo

YOLO segmentation format:
    Her satir: class_id x1 y1 x2 y2 ... xn yn
    Tum koordinatlar [0, 1] araliginda normalize edilmis poligon noktalari.
"""
import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image
from tqdm import tqdm


# CarDD'deki resmi sinif sirasi (kategori id'leri 1'den baslayabilir, biz 0-tabanli yapacagiz)
CARDD_CLASSES = ["dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat"]


def coco_polygon_to_yolo(polygon, img_w, img_h):
    """COCO formatindaki bir poligon listesini YOLO normalize formatina cevir.

    COCO: [[x1, y1, x2, y2, ...]] (kuçuk listeler poligonu temsil eder)
    YOLO: tek satirda x1/w y1/h x2/w y2/h ... [0,1] arasinda
    """
    if not polygon or len(polygon) == 0:
        return None
    # Cogu CarDD annotation tek poligonludur. Coklu varsa en buyugunu al.
    if isinstance(polygon[0], list):
        poly = max(polygon, key=len)
    else:
        poly = polygon

    # Tek nokta olmaz; en az 3 nokta = 6 koordinat
    if len(poly) < 6:
        return None

    normalized = []
    for i in range(0, len(poly), 2):
        x = poly[i] / img_w
        y = poly[i + 1] / img_h
        # Sinir clip
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        normalized.extend([x, y])
    return normalized


def convert_split(split_name, coco_json, img_src_dir, img_dst_dir, lbl_dst_dir,
                  category_id_to_idx):
    """Bir split (train/val/test) icin COCO -> YOLO donusumu yapar."""
    img_dst_dir.mkdir(parents=True, exist_ok=True)
    lbl_dst_dir.mkdir(parents=True, exist_ok=True)

    with open(coco_json, "r") as f:
        coco = json.load(f)

    # ID -> image dict
    images = {img["id"]: img for img in coco["images"]}

    # Image ID -> liste of annotations
    img_anns = {}
    for ann in coco["annotations"]:
        img_anns.setdefault(ann["image_id"], []).append(ann)

    class_counter = Counter()
    skipped = 0
    processed = 0

    for img_id, img_info in tqdm(images.items(), desc=f"{split_name}"):
        fname = img_info["file_name"]
        src_path = img_src_dir / fname
        if not src_path.exists():
            # Bazi CarDD klasoru farkli isimde olabilir
            skipped += 1
            continue

        # Goruntuyu kopyala (sembolik link daha hizli, OS'a gore degisir)
        dst_img_path = img_dst_dir / fname
        if not dst_img_path.exists():
            shutil.copy2(src_path, dst_img_path)

        # Boyut COCO json'da gelir ama dogrula
        img_w = img_info.get("width")
        img_h = img_info.get("height")
        if not img_w or not img_h:
            with Image.open(src_path) as im:
                img_w, img_h = im.size

        # YOLO label dosyasi
        lbl_path = lbl_dst_dir / (Path(fname).stem + ".txt")
        lines = []
        for ann in img_anns.get(img_id, []):
            cat_id = ann["category_id"]
            if cat_id not in category_id_to_idx:
                continue
            yolo_idx = category_id_to_idx[cat_id]

            polygon = ann.get("segmentation")
            if polygon is None or len(polygon) == 0:
                continue
            norm = coco_polygon_to_yolo(polygon, img_w, img_h)
            if norm is None:
                continue

            coords_str = " ".join(f"{c:.6f}" for c in norm)
            lines.append(f"{yolo_idx} {coords_str}")
            class_counter[CARDD_CLASSES[yolo_idx]] += 1

        # Bos label dosyasi bile yaz (YOLO'nun background icin gerekli)
        with open(lbl_path, "w") as f:
            f.write("\n".join(lines))
        processed += 1

    print(f"\n[{split_name}] Islenen: {processed}, Atlanan: {skipped}")
    print(f"[{split_name}] Sinif dagilimi: {dict(class_counter)}")
    return class_counter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cardd_root", type=str, required=True,
                        help="CarDD_COCO klasoru (annotations/ ve train2017/ icerir)")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="YOLO formatli ciktinin yazilacagi klasor")
    args = parser.parse_args()

    cardd_root = Path(args.cardd_root)
    output_dir = Path(args.output_dir)

    # Once category id eslemesini ogren (CarDD'de 1-6 idi)
    with open(cardd_root / "annotations" / "instances_train2017.json") as f:
        train_coco = json.load(f)
    categories = sorted(train_coco["categories"], key=lambda c: c["id"])
    print("CarDD kategorileri:")
    for c in categories:
        print(f"  id={c['id']}  name={c['name']}")

    # COCO category id -> 0-tabanli YOLO index
    # CarDD'nin standart sirasiyla esletiriz
    category_id_to_idx = {}
    for c in categories:
        name_normalized = c["name"].lower().replace(" ", "_")
        if name_normalized in CARDD_CLASSES:
            category_id_to_idx[c["id"]] = CARDD_CLASSES.index(name_normalized)
        else:
            print(f"UYARI: bilinmeyen kategori: {c['name']}")

    print(f"\nCategory id -> YOLO index esleme: {category_id_to_idx}\n")

    # Her split'i isle
    splits = [
        ("train", "instances_train2017.json", "train2017"),
        ("val", "instances_val2017.json", "val2017"),
        ("test", "instances_test2017.json", "test2017"),
    ]

    total_counter = Counter()
    for split_name, ann_file, img_subdir in splits:
        ann_path = cardd_root / "annotations" / ann_file
        img_src = cardd_root / img_subdir
        img_dst = output_dir / "images" / split_name
        lbl_dst = output_dir / "labels" / split_name

        if not ann_path.exists():
            print(f"UYARI: {ann_path} bulunamadi, atlandi.")
            continue
        if not img_src.exists():
            print(f"UYARI: {img_src} bulunamadi, atlandi.")
            continue

        counter = convert_split(split_name, ann_path, img_src, img_dst, lbl_dst,
                                category_id_to_idx)
        total_counter.update(counter)

    # cardd.yaml dosyasini guncelle/yaz
    yaml_path = Path("cardd.yaml")
    yaml_content = f"""# YOLO segmentation veri konfigi - CarDD
# Otomatik olarak prepare_data.py tarafindan uretildi
path: {output_dir.resolve()}
train: images/train
val: images/val
test: images/test

# Sinif sayisi
nc: {len(CARDD_CLASSES)}

# Sinif isimleri (0-tabanli sira)
names:
"""
    for idx, name in enumerate(CARDD_CLASSES):
        yaml_content += f"  {idx}: {name}\n"

    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    print(f"\n=== Donusum tamamlandi ===")
    print(f"Cikti: {output_dir.resolve()}")
    print(f"Veri konfigi: {yaml_path.resolve()}")
    print(f"Toplam etiket: {dict(total_counter)}")
    print(f"\nSonraki adim: python train.py --data {yaml_path} --model yolo26n-seg --epochs 50")


if __name__ == "__main__":
    main()
