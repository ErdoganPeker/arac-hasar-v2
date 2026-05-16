"""
train_severity.py — 3-class car damage severity CNN classifier

EfficientNet-B0 (small, fast) fine-tuned on CSP650 Car Damage Severity Assessment dataset.
3 classes: minor / moderate / severe -> mapped to Turkish: hafif / orta / agir.

Usage:
    python train_severity.py [--epochs 30] [--batch 32] [--lr 0.0003]

Saves best.pt to services/ml/runs/severity/.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights

# Roboflow class names -> Turkish severity levels
CLASS_NAME_MAP = {
    "01-minor": "hafif",
    "02-moderate": "orta",
    "03-severe": "agir",
}


def get_transforms(img_size: int = 224):
    train_tf = transforms.Compose([
        transforms.Resize((img_size + 32, img_size + 32)),
        transforms.RandomCrop(img_size),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        transforms.RandomRotation(15),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    return train_tf, val_tf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_root", type=Path,
                    default=Path("data/severity_roboflow/Car-Damage-Severity-Assessment-6"))
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--img_size", type=int, default=224)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--output_dir", type=Path, default=Path("runs/severity"))
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    train_tf, val_tf = get_transforms(args.img_size)

    train_ds = datasets.ImageFolder(args.data_root / "train", transform=train_tf)
    val_ds = datasets.ImageFolder(args.data_root / "valid", transform=val_tf)
    test_ds = datasets.ImageFolder(args.data_root / "test", transform=val_tf)

    print(f"Classes: {train_ds.classes}")
    print(f"Train: {len(train_ds)}, Val: {len(val_ds)}, Test: {len(test_ds)}")

    # Map class indices to Turkish names for inference
    tr_names = [CLASS_NAME_MAP.get(c, c) for c in train_ds.classes]
    print(f"Turkish: {tr_names}")

    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True,
                              num_workers=args.workers, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch, shuffle=False,
                            num_workers=args.workers, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch, shuffle=False,
                             num_workers=args.workers, pin_memory=True)

    # Model: EfficientNet-B0 pretrained, replace classifier head
    weights = EfficientNet_B0_Weights.IMAGENET1K_V1
    model = efficientnet_b0(weights=weights)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, 3)
    model = model.to(args.device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_acc = 0.0
    history = []

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        for x, y in train_loader:
            x, y = x.to(args.device, non_blocking=True), y.to(args.device, non_blocking=True)
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * x.size(0)
            train_correct += (out.argmax(1) == y).sum().item()
            train_total += x.size(0)
        train_loss /= train_total
        train_acc = train_correct / train_total

        model.eval()
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(args.device, non_blocking=True), y.to(args.device, non_blocking=True)
                out = model(x)
                val_correct += (out.argmax(1) == y).sum().item()
                val_total += x.size(0)
        val_acc = val_correct / val_total

        scheduler.step()
        dt = time.time() - t0
        print(f"Epoch {epoch:3d}/{args.epochs} | loss={train_loss:.4f} | "
              f"train_acc={train_acc:.4f} | val_acc={val_acc:.4f} | {dt:.1f}s")
        history.append({
            "epoch": epoch, "train_loss": train_loss,
            "train_acc": train_acc, "val_acc": val_acc, "duration_s": dt,
        })

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            ckpt = {
                "model_state_dict": model.state_dict(),
                "classes": train_ds.classes,
                "tr_names": tr_names,
                "val_acc": val_acc,
                "epoch": epoch,
                "img_size": args.img_size,
                "arch": "efficientnet_b0",
            }
            torch.save(ckpt, args.output_dir / "best.pt")

    # Final test evaluation with best checkpoint
    ckpt = torch.load(args.output_dir / "best.pt", weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    test_correct = 0
    test_total = 0
    cm = torch.zeros(3, 3, dtype=torch.long)
    with torch.no_grad():
        for x, y in test_loader:
            x, y = x.to(args.device), y.to(args.device)
            preds = model(x).argmax(1)
            test_correct += (preds == y).sum().item()
            test_total += x.size(0)
            for t, p in zip(y.cpu(), preds.cpu()):
                cm[t, p] += 1
    test_acc = test_correct / test_total
    print(f"\n=== Test acc: {test_acc:.4f} | best val: {best_val_acc:.4f} ===")
    print("Confusion matrix (rows=truth, cols=pred):")
    print(cm.numpy())

    (args.output_dir / "history.json").write_text(
        json.dumps({"history": history, "test_acc": test_acc,
                    "best_val_acc": best_val_acc, "classes": train_ds.classes,
                    "tr_names": tr_names, "confusion": cm.tolist()},
                   indent=2)
    )
    print(f"\nBest weights: {args.output_dir / 'best.pt'}")
    print(f"History: {args.output_dir / 'history.json'}")


if __name__ == "__main__":
    main()
