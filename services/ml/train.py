"""
train.py
YOLO26-seg modelini CarDD veri seti uzerinde egitir.

Ornek kullanim:
    # Hizli baseline (15-30 dk)
    python train.py --model yolo26n-seg --epochs 50 --imgsz 640

    # Ana egitim (4-8 saat, RTX 4090)
    python train.py --model yolo26m-seg --epochs 150 --imgsz 640 --batch 16

    # Yuksek cozunurluk (kucuk hasarlar icin)
    python train.py --model yolo26m-seg --epochs 200 --imgsz 1024 --batch 8

W&B kullanmak icin: export WANDB_API_KEY=... ve --wandb argümani ver.
"""
import argparse
from pathlib import Path

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()

    # Temel argumanlar
    parser.add_argument("--data", type=str, default="cardd.yaml")
    parser.add_argument("--model", type=str, default="yolo26m-seg",
                        choices=["yolo26n-seg", "yolo26s-seg", "yolo26m-seg",
                                 "yolo26l-seg", "yolo26x-seg",
                                 "yolo11n-seg", "yolo11m-seg"])
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--device", type=str, default="0",
                        help="'0' tek GPU, '0,1' coklu, 'cpu' CPU")

    # Optimizer
    parser.add_argument("--optimizer", type=str, default="AdamW",
                        choices=["SGD", "Adam", "AdamW"])
    parser.add_argument("--lr0", type=float, default=0.001)
    parser.add_argument("--lrf", type=float, default=0.01,
                        help="Final learning rate factor")
    parser.add_argument("--weight_decay", type=float, default=0.0005)
    parser.add_argument("--momentum", type=float, default=0.937)
    parser.add_argument("--warmup_epochs", type=float, default=3.0)

    # Augmentation - kucuk nesne tespiti icin onemli
    parser.add_argument("--mosaic", type=float, default=1.0,
                        help="Mosaic augmentation olasiligi")
    parser.add_argument("--mixup", type=float, default=0.1)
    parser.add_argument("--copy_paste", type=float, default=0.3,
                        help="Segmentation icin onemli - hasarlari farkli aracara kopyalar")
    parser.add_argument("--hsv_h", type=float, default=0.015)
    parser.add_argument("--hsv_s", type=float, default=0.7)
    parser.add_argument("--hsv_v", type=float, default=0.5,
                        help="Brightness varyasyonu - gunes/golge robust olmak icin artir")
    parser.add_argument("--degrees", type=float, default=10.0)
    parser.add_argument("--translate", type=float, default=0.1)
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--fliplr", type=float, default=0.5)

    # Eğitim davranisi
    parser.add_argument("--patience", type=int, default=50,
                        help="Early stopping icin patience")
    parser.add_argument("--save_period", type=int, default=10)
    parser.add_argument("--name", type=str, default=None,
                        help="Run ismi (runs/segment/<name>)")
    parser.add_argument("--resume", action="store_true")

    # Logging
    parser.add_argument("--wandb", action="store_true",
                        help="Weights & Biases kullan")
    parser.add_argument("--project", type=str, default="arac-hasar")

    args = parser.parse_args()

    # Run ismi - argumanlar yansisin
    if args.name is None:
        args.name = f"{args.model}_ep{args.epochs}_sz{args.imgsz}_bs{args.batch}"

    print(f"=== Egitim Konfigi ===")
    for k, v in vars(args).items():
        print(f"  {k}: {v}")
    print()

    # Pretrained model yukle
    model = YOLO(f"{args.model}.pt")

    # Egitim
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,

        optimizer=args.optimizer,
        lr0=args.lr0,
        lrf=args.lrf,
        weight_decay=args.weight_decay,
        momentum=args.momentum,
        warmup_epochs=args.warmup_epochs,

        mosaic=args.mosaic,
        mixup=args.mixup,
        copy_paste=args.copy_paste,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        degrees=args.degrees,
        translate=args.translate,
        scale=args.scale,
        fliplr=args.fliplr,

        patience=args.patience,
        save_period=args.save_period,
        project=f"runs/{args.project}",
        name=args.name,
        resume=args.resume,

        # YOLO26 spesifik / pratik flag'ler
        amp=True,           # Mixed precision - hizlandirir, VRAM tasarrufu
        cache=False,        # RAM yeterli ise True yapabilirsin (10x hizlanir)
        plots=True,         # Validation sonunda confusion matrix, PR egrisi vs.
        verbose=True,
    )

    print(f"\n=== Egitim tamamlandi ===")
    print(f"En iyi model: {Path(results.save_dir) / 'weights' / 'best.pt'}")
    print(f"\nSonraki adim:")
    print(f"  python evaluate.py --weights {Path(results.save_dir) / 'weights' / 'best.pt'} \\")
    print(f"      --data {args.data} --split test")


if __name__ == "__main__":
    main()
