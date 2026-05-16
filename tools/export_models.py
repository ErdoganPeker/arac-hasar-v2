"""
export_models.py
Egitilmis YOLO26 modelini mobil/edge formatlarina export eder.

Desteklenen formatlar:
  - tflite: Android, INT8 quantization destekli
  - coreml: iOS, FP16 onerilen
  - onnx:   Cross-platform, ONNX Runtime icin
  - openvino: Intel CPU/iGPU
  - engine: NVIDIA TensorRT

Kullanim:
    # Android icin INT8 TFLite (kucuk + hizli)
    python export_models.py --weights runs/.../best.pt \
        --format tflite --imgsz 320 --int8

    # iOS icin CoreML FP16
    python export_models.py --weights runs/.../best.pt \
        --format coreml --imgsz 320 --half

    # Server icin ONNX
    python export_models.py --weights runs/.../best.pt \
        --format onnx --imgsz 640
"""
import argparse
from pathlib import Path

from ultralytics import YOLO


def export(weights, format_name, imgsz=640, int8=False, half=False, data=None,
           dynamic=False, simplify=True):
    """YOLO26 modelini istenen formata export eder."""
    print(f"Yukleniyor: {weights}")
    model = YOLO(weights)

    kwargs = {
        "format": format_name,
        "imgsz": imgsz,
        "half": half,
        "int8": int8,
        "dynamic": dynamic,
        "simplify": simplify,
    }
    if data and int8:
        # INT8 icin calibration veri seti gerekir
        kwargs["data"] = data

    print(f"Export ediliyor: format={format_name}, imgsz={imgsz}, int8={int8}, half={half}")
    output_path = model.export(**kwargs)
    print(f"\nBasarili: {output_path}")
    return output_path


def benchmark_exported(model_path, imgsz=320, runs=50):
    """Export edilmis modelin hizini olcer."""
    import time
    import numpy as np

    print(f"\nBenchmark: {model_path}")
    try:
        model = YOLO(model_path)
        dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)

        # Warm-up
        for _ in range(5):
            model.predict(dummy, verbose=False)

        # Olc
        start = time.time()
        for _ in range(runs):
            model.predict(dummy, verbose=False)
        elapsed = time.time() - start
        ms_per_image = elapsed * 1000 / runs

        print(f"  Ortalama: {ms_per_image:.2f} ms/image")
        print(f"  FPS: {1000 / ms_per_image:.1f}")
    except Exception as e:
        print(f"  Benchmark basarisiz: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, required=True,
                        help=".pt model dosyasi")
    parser.add_argument("--format", type=str, default="tflite",
                        choices=["tflite", "coreml", "onnx", "openvino", "engine",
                                 "torchscript", "saved_model"])
    parser.add_argument("--imgsz", type=int, default=320,
                        help="Mobile icin 320 onerilir, server icin 640")
    parser.add_argument("--int8", action="store_true",
                        help="INT8 quantization (mobile icin)")
    parser.add_argument("--half", action="store_true",
                        help="FP16 (iOS Neural Engine icin)")
    parser.add_argument("--dynamic", action="store_true")
    parser.add_argument("--data", type=str, default=None,
                        help="INT8 calibration icin data yaml")
    parser.add_argument("--benchmark", action="store_true",
                        help="Export sonrasi benchmark koc")

    args = parser.parse_args()

    output_path = export(
        weights=args.weights,
        format_name=args.format,
        imgsz=args.imgsz,
        int8=args.int8,
        half=args.half,
        dynamic=args.dynamic,
        data=args.data,
    )

    if args.benchmark:
        benchmark_exported(output_path, imgsz=args.imgsz)

    # Mobile entegrasyon notlari
    print("\n=== Sonraki Adim ===")
    if args.format == "tflite":
        print("Android entegrasyonu:")
        print("  - mobile/assets/models/ klasorune kopyala")
        print("  - react-native-fast-tflite ile yukle")
        print("  - imgsz=320 icin input shape [1, 320, 320, 3] uint8")
    elif args.format == "coreml":
        print("iOS entegrasyonu:")
        print("  - .mlpackage dosyasini Xcode projesine drag-drop et")
        print("  - Vision framework ile inference")
        print("  - Apple Neural Engine'in tum gucunu kullan")
    elif args.format == "onnx":
        print("Server/desktop:")
        print("  - onnxruntime ile yukle: pip install onnxruntime-gpu")
        print("  - Triton Inference Server icin uygun")


if __name__ == "__main__":
    main()
