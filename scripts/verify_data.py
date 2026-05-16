"""
verify_data.py
Yerel veri klasorlerini tarayip integrity raporu uretir.

Kullanim:
    python scripts/verify_data.py --help
    python scripts/verify_data.py
    python scripts/verify_data.py --check-images   # PIL ile her goruntuyu ac
    python scripts/verify_data.py --json out.json  # makinece okunabilir cikti

Kontroller:
- services/ml/data/cardd_hf/        var mi, dosya sayisi
- services/ml/data/CarDD_release/   COCO json'lari var mi
- services/ml/data/cardd_yolo/      images/* + labels/* sayilar
- services/ml/data/parts_yolo/      images/* + labels/* sayilar
- services/ml/data/severity_roboflow/ data.yaml var mi
- services/ml/weights/              .pt dosya listesi + boyut
- Etiket dosyalarinin format kontrolu (0-tabanli sinif, normalize koord)
- Bos / 0 byte / kirik goruntu sayisi
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ML_ROOT = PROJECT_ROOT / "services" / "ml"
DATA_ROOT = ML_ROOT / "data"
WEIGHTS_DIR = ML_ROOT / "weights"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = ("train", "val", "test")


@dataclass
class SplitStats:
    images: int = 0
    labels: int = 0
    empty_labels: int = 0
    invalid_labels: int = 0
    zero_byte_images: int = 0
    broken_images: int = 0
    class_distribution: Dict[str, int] = field(default_factory=dict)


@dataclass
class DatasetReport:
    name: str
    root: str
    exists: bool
    splits: Dict[str, SplitStats] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def is_label_line_valid(line: str) -> bool:
    """YOLO seg satiri: 'cls x1 y1 x2 y2 ...' tum koordlar [0,1]."""
    parts = line.strip().split()
    if len(parts) < 7:  # cls + en az 3 nokta
        return False
    try:
        cls = int(parts[0])
        if cls < 0:
            return False
        coords = [float(x) for x in parts[1:]]
        if len(coords) % 2 != 0:
            return False
        if any(c < -0.001 or c > 1.001 for c in coords):
            return False
    except ValueError:
        return False
    return True


def scan_yolo_split(img_dir: Path, lbl_dir: Path,
                    check_images: bool = False) -> SplitStats:
    s = SplitStats()
    if not img_dir.exists():
        return s

    images = [p for p in img_dir.iterdir()
              if p.is_file() and p.suffix.lower() in IMG_EXTS]
    s.images = len(images)

    if check_images:
        try:
            from PIL import Image
        except ImportError:
            Image = None
        for p in images:
            try:
                if p.stat().st_size == 0:
                    s.zero_byte_images += 1
                    continue
                if Image is None:
                    continue
                with Image.open(p) as im:
                    im.verify()
            except Exception:
                s.broken_images += 1

    if lbl_dir.exists():
        labels = list(lbl_dir.glob("*.txt"))
        s.labels = len(labels)
        class_counter: Counter = Counter()
        for lp in labels:
            try:
                txt = lp.read_text(encoding="utf-8")
            except Exception:
                s.invalid_labels += 1
                continue
            stripped = txt.strip()
            if not stripped:
                s.empty_labels += 1
                continue
            file_ok = True
            for line in stripped.splitlines():
                if not line.strip():
                    continue
                if not is_label_line_valid(line):
                    file_ok = False
                    break
                cls = line.strip().split()[0]
                class_counter[cls] += 1
            if not file_ok:
                s.invalid_labels += 1
        s.class_distribution = dict(class_counter)

    return s


def scan_yolo_dataset(name: str, root: Path, check_images: bool) -> DatasetReport:
    rep = DatasetReport(name=name, root=str(root), exists=root.exists())
    if not rep.exists:
        rep.notes.append("Klasor yok — ilgili indirme/prepare adimi calistirilmamis.")
        return rep
    for split in SPLITS:
        img_dir = root / "images" / split
        lbl_dir = root / "labels" / split
        rep.splits[split] = scan_yolo_split(img_dir, lbl_dir, check_images)
    return rep


def scan_cardd_hf(check_images: bool) -> DatasetReport:
    root = DATA_ROOT / "cardd_hf"
    rep = DatasetReport(name="cardd_hf (HuggingFace mirror)",
                        root=str(root), exists=root.exists())
    if not rep.exists:
        rep.notes.append("Indir: python scripts/download_data.py --cardd-hf")
        return rep
    files = list(root.rglob("*"))
    images = [f for f in files if f.suffix.lower() in IMG_EXTS]
    rep.notes.append(f"Toplam dosya: {len(files)}, goruntu: {len(images)}")
    return rep


def scan_cardd_release() -> DatasetReport:
    root = DATA_ROOT / "CarDD_release"
    rep = DatasetReport(name="CarDD_release (manuel, form sonrasi)",
                        root=str(root), exists=root.exists())
    if not rep.exists:
        rep.notes.append(
            "Form basvurusu: https://cardd-ustc.github.io | Indirince: "
            "python scripts/download_data.py --cardd-manual <ZIP>")
        return rep
    coco_root_candidates = list(root.glob("**/CarDD_COCO"))
    coco_root = coco_root_candidates[0] if coco_root_candidates else root / "CarDD_COCO"
    rep.notes.append(f"CarDD_COCO: {coco_root} (var: {coco_root.exists()})")
    ann_dir = coco_root / "annotations"
    if ann_dir.exists():
        for split, fname in [("train", "instances_train2017.json"),
                             ("val", "instances_val2017.json"),
                             ("test", "instances_test2017.json")]:
            p = ann_dir / fname
            rep.notes.append(f"{split}: {p.name} {'OK' if p.exists() else 'EKSIK'}")
    return rep


def scan_severity() -> DatasetReport:
    root = DATA_ROOT / "severity_roboflow"
    rep = DatasetReport(name="severity_roboflow",
                        root=str(root), exists=root.exists())
    if not rep.exists:
        rep.notes.append(
            "Indir: python scripts/download_data.py --roboflow-severity "
            "(ROBOFLOW_API_KEY gerekli)")
        return rep
    yaml_files = list(root.glob("**/data.yaml"))
    rep.notes.append(f"data.yaml sayisi: {len(yaml_files)}")
    images = list(root.rglob("*.jpg")) + list(root.rglob("*.png"))
    rep.notes.append(f"goruntu: {len(images)}")
    return rep


def scan_weights() -> DatasetReport:
    root = WEIGHTS_DIR
    rep = DatasetReport(name="weights/", root=str(root), exists=root.exists())
    if not rep.exists:
        rep.notes.append("Indir: python scripts/download_pretrained.py --all")
        return rep
    pts = list(root.glob("*.pt"))
    if not pts:
        rep.notes.append("Hicbir .pt yok.")
    for p in sorted(pts):
        mb = p.stat().st_size / 1024 / 1024
        rep.notes.append(f"  {p.name}  {mb:.1f} MB")
    return rep


def render_text(reports: List[DatasetReport]) -> str:
    out = []
    out.append("=" * 78)
    out.append("VERI INTEGRITY RAPORU")
    out.append("=" * 78)
    for r in reports:
        out.append("")
        marker = "OK" if r.exists else "EKSIK"
        out.append(f"[{marker}] {r.name}")
        out.append(f"  yol: {r.root}")
        if r.splits:
            for split, s in r.splits.items():
                if s.images == 0 and s.labels == 0:
                    continue
                out.append(
                    f"  {split:5s}  img={s.images:6d}  lbl={s.labels:6d}  "
                    f"empty={s.empty_labels}  invalid={s.invalid_labels}  "
                    f"broken_img={s.broken_images}  zero_byte={s.zero_byte_images}"
                )
                if s.class_distribution:
                    top = ", ".join(f"{k}={v}" for k, v in
                                    sorted(s.class_distribution.items(),
                                           key=lambda kv: int(kv[0]))[:8])
                    out.append(f"    cls: {top}")
        for n in r.notes:
            out.append(f"  - {n}")
    out.append("")
    out.append("=" * 78)
    out.append("SONRAKI ADIM ONERILERI")
    out.append("=" * 78)
    have = {r.name.split()[0]: r.exists for r in reports}
    if not have.get("cardd_hf", False) and not have.get("CarDD_release", False):
        out.append("- CarDD yok: 'python scripts/download_data.py --cardd-hf' ile basla.")
    if not have.get("weights/", False):
        out.append("- weights/ bos: 'python scripts/download_pretrained.py --all'.")
    out.append("- Tum data ready ise: services/ml/prepare_data.py + train.py")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="services/ml/data ve weights/ klasorlerini dogrula",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--check-images", action="store_true",
                   help="PIL ile her goruntuyu ac/dogrula (yavas)")
    p.add_argument("--json", type=str, default=None,
                   help="Raporu JSON dosyasina yaz")
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)

    reports: List[DatasetReport] = []
    reports.append(scan_cardd_hf(args.check_images))
    reports.append(scan_cardd_release())
    reports.append(scan_yolo_dataset("cardd_yolo (prepare_data.py ciktisi)",
                                     DATA_ROOT / "cardd_yolo", args.check_images))
    reports.append(scan_yolo_dataset("parts_yolo (prepare_parts_data.py ciktisi)",
                                     DATA_ROOT / "parts_yolo", args.check_images))
    reports.append(scan_severity())
    reports.append(scan_weights())

    text = render_text(reports)
    print(text)

    if args.json:
        out = {"reports": [
            {**asdict(r), "splits": {k: asdict(v) for k, v in r.splits.items()}}
            for r in reports
        ]}
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nJSON yazildi: {args.json}")

    # Hicbir set yoksa exit=2, kismi varsa 0
    if not any(r.exists for r in reports):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
