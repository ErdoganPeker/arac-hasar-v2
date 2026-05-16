"""
onnx_export.py - Export the three trained YOLO models to ONNX for desktop/mobile.

Outputs go to:
    <snapshot>/onnx/damage.onnx
    <snapshot>/onnx/parts.onnx
    <snapshot>/onnx/severity.onnx

Each export:
  - Uses imgsz=640 (mobile/desktop friendly; cls model uses 224)
  - opset=12 (broad runtime compatibility, includes Core ML / NNAPI)
  - dynamic batch where supported
  - simplified=True via onnx-simplifier (Ultralytics handles this)

After export, the script attempts to load each .onnx with onnxruntime and
runs a dummy forward pass as a smoke test.

Usage:
    python onnx_export.py
    python onnx_export.py --imgsz 640 --opset 12
    python onnx_export.py --no-smoke-test
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


logger = logging.getLogger(__name__)


# Default snapshot directory (frozen, see task brief)
DEFAULT_SNAPSHOT = (
    Path(__file__).resolve().parent
    / "runs" / "bundles" / "full_20260515_044630" / "_SNAPSHOT_FOR_BUILD"
)


def _is_torchvision_ckpt(weights: Path) -> bool:
    """Return True if the .pt file is a custom torchvision checkpoint dict
    (from train_severity.py) rather than an Ultralytics YOLO file."""
    try:
        import torch
        ckpt = torch.load(str(weights), map_location="cpu", weights_only=False)
        return isinstance(ckpt, dict) and "model_state_dict" in ckpt
    except Exception:
        return False


def _export_torchvision_efficientnet(weights: Path,
                                     out_path: Path,
                                     imgsz: int,
                                     opset: int,
                                     dynamic: bool) -> Path:
    """Export a custom EfficientNet-B0 severity checkpoint to ONNX."""
    import torch
    import torch.nn as nn
    from torchvision.models import efficientnet_b0

    ckpt = torch.load(str(weights), map_location="cpu", weights_only=False)
    arch = ckpt.get("arch", "efficientnet_b0")
    if arch != "efficientnet_b0":
        raise ValueError(f"Unsupported torchvision arch for ONNX export: {arch}")

    n_classes = len(ckpt.get("classes", []))
    model = efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, n_classes)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    img_size = int(ckpt.get("img_size", imgsz))
    dummy = torch.zeros(1, 3, img_size, img_size, dtype=torch.float32)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    dyn_axes = {"input": {0: "batch"}, "output": {0: "batch"}} if dynamic else None

    # Use the legacy exporter (`dynamo=False`) to avoid the new exporter's
    # unicode-heavy stdout that crashes on Windows cp1252 consoles, and to
    # keep opset compatibility broad.
    export_kwargs = dict(
        input_names=["input"],
        output_names=["output"],
        opset_version=opset,
        do_constant_folding=True,
        dynamic_axes=dyn_axes,
    )
    try:
        torch.onnx.export(model, dummy, str(out_path), dynamo=False, **export_kwargs)
    except TypeError:
        # Older torch without `dynamo` kwarg
        torch.onnx.export(model, dummy, str(out_path), **export_kwargs)
    logger.info("Wrote %s (%.1f MB) [torchvision/efficientnet_b0]",
                out_path, out_path.stat().st_size / 1e6)
    return out_path


def export_one(weights: Path,
               out_path: Path,
               imgsz: int,
               opset: int,
               half: bool = False,
               dynamic: bool = True,
               simplify: bool = True) -> Path:
    """Export a single .pt model to ONNX, then move into out_path."""
    logger.info("Exporting %s -> %s (imgsz=%d, opset=%d)", weights.name, out_path, imgsz, opset)

    # Detect custom torchvision-style checkpoints (e.g. severity)
    if _is_torchvision_ckpt(weights):
        return _export_torchvision_efficientnet(
            weights=weights, out_path=out_path,
            imgsz=imgsz, opset=opset, dynamic=dynamic,
        )

    from ultralytics import YOLO  # imported lazily
    model = YOLO(str(weights))

    # Ultralytics writes the .onnx next to the .pt by default
    exported = model.export(
        format="onnx",
        imgsz=imgsz,
        opset=opset,
        dynamic=dynamic,
        simplify=simplify,
        half=half,
        device="cpu",  # CPU export is fine; runtime can be anything
    )

    if isinstance(exported, (list, tuple)):
        exported = exported[0]
    exported = Path(exported)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if exported.resolve() != out_path.resolve():
        shutil.move(str(exported), str(out_path))
    logger.info("Wrote %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
    return out_path


def smoke_test_onnx(onnx_path: Path, imgsz: int, is_cls: bool = False) -> Dict:
    """Load with onnxruntime and run a dummy forward pass."""
    try:
        import onnx  # noqa: F401
        import onnxruntime as ort
    except ImportError as exc:
        return {"ok": False, "error": f"onnx/onnxruntime not installed: {exc}"}

    try:
        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        inputs = sess.get_inputs()
        outputs = sess.get_outputs()
        input_name = inputs[0].name
        # Dummy input: NCHW, float32, 0..1
        size = 224 if is_cls else imgsz
        dummy = np.random.rand(1, 3, size, size).astype(np.float32)
        t0 = time.perf_counter()
        out = sess.run(None, {input_name: dummy})
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "ok": True,
            "input_shape": list(dummy.shape),
            "input_name": input_name,
            "output_names": [o.name for o in outputs],
            "output_shapes": [list(o.shape) for o in outputs],
            "first_output_shape": list(out[0].shape) if out else None,
            "cpu_inference_ms": round(elapsed, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Export YOLO models to ONNX.")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT,
                        help="Snapshot directory containing the three .pt files.")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="Detection/seg image size. Severity uses 224.")
    parser.add_argument("--severity-imgsz", type=int, default=224)
    parser.add_argument("--opset", type=int, default=12)
    parser.add_argument("--no-dynamic", action="store_true")
    parser.add_argument("--no-simplify", action="store_true")
    parser.add_argument("--half", action="store_true",
                        help="Export FP16 (smaller, GPU-only at runtime).")
    parser.add_argument("--no-smoke-test", action="store_true")
    parser.add_argument("--only", choices=["damage", "parts", "severity"], default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")

    snap = args.snapshot.resolve()
    if not snap.exists():
        logger.error("Snapshot dir not found: %s", snap)
        sys.exit(1)

    out_dir = snap / "onnx"
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        ("damage",   snap / "damage_best.pt",   out_dir / "damage.onnx",   args.imgsz,            False),
        ("parts",    snap / "parts_best.pt",    out_dir / "parts.onnx",    args.imgsz,            False),
        ("severity", snap / "severity_best.pt", out_dir / "severity.onnx", args.severity_imgsz,  True),
    ]
    if args.only:
        targets = [t for t in targets if t[0] == args.only]

    report: List[Dict] = []
    for name, weights, onnx_out, imgsz, is_cls in targets:
        entry: Dict = {"name": name, "weights": str(weights), "onnx": str(onnx_out)}
        if not weights.exists():
            entry.update({"ok": False, "error": "weights file not found"})
            report.append(entry)
            continue
        try:
            export_one(
                weights=weights,
                out_path=onnx_out,
                imgsz=imgsz,
                opset=args.opset,
                half=args.half,
                dynamic=not args.no_dynamic,
                simplify=not args.no_simplify,
            )
            entry["ok"] = True
            entry["size_mb"] = round(onnx_out.stat().st_size / 1e6, 2)
            if not args.no_smoke_test:
                entry["smoke"] = smoke_test_onnx(onnx_out, imgsz=imgsz, is_cls=is_cls)
        except Exception as exc:  # noqa: BLE001
            logger.exception("export failed for %s", name)
            entry.update({"ok": False, "error": str(exc)})
        report.append(entry)

    print("\n=== ONNX Export Report ===")
    for r in report:
        flag = "OK" if r.get("ok") else "FAIL"
        line = f"  [{flag}] {r['name']:<10} -> {Path(r['onnx']).name}"
        if r.get("ok"):
            line += f"  ({r.get('size_mb')} MB)"
            smoke = r.get("smoke") or {}
            if smoke.get("ok"):
                line += f"  smoke OK ({smoke['cpu_inference_ms']} ms cpu)"
            elif smoke:
                line += f"  smoke FAIL: {smoke.get('error')}"
        else:
            line += f"  ERROR: {r.get('error')}"
        print(line)

    failed = [r for r in report if not r.get("ok")]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
