"""
train_parts.py
Parca segmentasyonu icin YOLO26-seg egitir.
train.py ile cogu argumani paylasir; ozel olarak class_weights destegi var.

Kullanim:
    python train_parts.py --data parts.yaml --model yolo26m-seg --epochs 150
"""
import argparse
from pathlib import Path

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="parts.yaml")
    parser.add_argument("--model", type=str, default="yolo26m-seg")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", type=str, default="0")

    # Parca-spesifik: minor parts (mirror, light) icin daha agresif aug
    parser.add_argument("--copy_paste", type=float, default=0.5,
                        help="Parca segmentasyonunda yuksek tutmak iyidir")
    parser.add_argument("--mosaic", type=float, default=1.0)
    parser.add_argument("--mixup", type=float, default=0.15)

    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--name", type=str, default=None)
    args = parser.parse_args()

    if args.name is None:
        args.name = f"parts_{args.model}_ep{args.epochs}"

    model = YOLO(f"{args.model}.pt")

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        optimizer="AdamW",
        lr0=0.001,
        weight_decay=0.0005,
        mosaic=args.mosaic,
        mixup=args.mixup,
        copy_paste=args.copy_paste,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.5,
        degrees=15.0,        # Parcalar farkli acilardan gelir
        translate=0.15,
        scale=0.6,
        fliplr=0.5,
        patience=args.patience,
        amp=True,
        plots=True,
        project="runs/arac-hasar",
        name=args.name,
    )

    print(f"\n=== Egitim tamamlandi ===")
    print(f"En iyi: {Path(results.save_dir) / 'weights' / 'best.pt'}")


if __name__ == "__main__":
    main()
