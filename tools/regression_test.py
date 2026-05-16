"""
tests/regression_test.py
Regression test suite - her PR'da koc, yeni modelin eskine gore degisimi olc.

Calistirma:
    # Mevcut prod modeli ile baseline kaydet
    python tests/regression_test.py --weights prod_best.pt --save_baseline

    # Yeni model versiyonunu test et
    python tests/regression_test.py --weights new_best.pt --compare_baseline

    # CI'da kullanim
    python tests/regression_test.py --weights $NEW_MODEL --compare_baseline \
        --fail_threshold 0.05
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import yaml


def load_test_cases(yaml_path):
    """test_cases.yaml'i yukle."""
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f)


def run_inference(pipeline, image_path):
    """Tek bir goruntude pipeline koc, ozet metrikleri dondur."""
    result = pipeline.analyze(str(image_path))
    summary = result.get("summary", {})
    return {
        "has_damage": summary.get("has_damage", False),
        "damage_count": result.get("damage_count", 0),
        "damage_types": sorted(set(d["type"] for d in result.get("damages", []))),
        "cost_min": summary.get("total_cost_range_tl", [0])[0],
        "cost_max": summary.get("total_cost_range_tl", [0, 0])[1],
        "most_severe": summary.get("most_severe"),
    }


def compare_to_expected(actual, expected, tolerance):
    """Beklenen vs gercek karsilastir. Hata varsa liste dondur."""
    errors = []

    # 1. Hasar var/yok dogru mu
    if "has_damage" in expected and actual["has_damage"] != expected["has_damage"]:
        errors.append(f"has_damage: beklenen={expected['has_damage']}, gercek={actual['has_damage']}")

    # 2. Hasar sayisi tolerans icinde mi
    if "damage_count" in expected:
        diff = abs(actual["damage_count"] - expected["damage_count"])
        if diff > expected.get("count_tolerance", 1):
            errors.append(f"damage_count: beklenen={expected['damage_count']}±{expected.get('count_tolerance', 1)}, gercek={actual['damage_count']}")

    # 3. Beklenen siniflari iceriyor mu
    if "must_contain_types" in expected:
        for t in expected["must_contain_types"]:
            if t not in actual["damage_types"]:
                errors.append(f"Beklenen tip eksik: {t}")

    # 4. Maliyet araliginda mi
    if "cost_range_check" in expected:
        cr = expected["cost_range_check"]
        if "min_below" in cr and actual["cost_min"] > cr["min_below"]:
            errors.append(f"cost_min cok yuksek: {actual['cost_min']:.0f} > {cr['min_below']}")
        if "max_above" in cr and actual["cost_max"] < cr["max_above"]:
            errors.append(f"cost_max cok dusuk: {actual['cost_max']:.0f} < {cr['max_above']}")

    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, required=True)
    parser.add_argument("--parts_weights", type=str, default=None)
    parser.add_argument("--severity_weights", type=str, default=None)
    parser.add_argument("--cases", type=str, default="tests/test_cases.yaml")
    parser.add_argument("--cost_table", type=str, default="cost_table.yaml")

    parser.add_argument("--save_baseline", action="store_true",
                        help="Bu kosumun sonucunu baseline olarak kaydet")
    parser.add_argument("--baseline_file", type=str, default="tests/baseline.json")
    parser.add_argument("--compare_baseline", action="store_true",
                        help="Baseline ile karsilastir, regresyonu raporla")
    parser.add_argument("--fail_threshold", type=float, default=0.10,
                        help="Bu oranin uzerinde test fail ederse exit 1")

    args = parser.parse_args()

    # Pipeline yukle
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pipeline import DamagePipeline

    pipeline = DamagePipeline(
        damage_weights=args.weights,
        parts_weights=args.parts_weights,
        severity_weights=args.severity_weights,
        cost_table=args.cost_table,
    )

    cases = load_test_cases(args.cases)
    print(f"\n=== Regression Test: {len(cases['cases'])} case ===\n")

    results = []
    failed = 0

    for case in cases["cases"]:
        case_id = case["id"]
        image_path = Path(case["image"])
        if not image_path.exists():
            print(f"[ATLA] {case_id}: goruntu bulunamadi: {image_path}")
            continue

        try:
            actual = run_inference(pipeline, image_path)
            errors = compare_to_expected(actual, case.get("expected", {}), 
                                          tolerance=case.get("tolerance", {}))

            status = "PASS" if not errors else "FAIL"
            if errors:
                failed += 1

            print(f"[{status}] {case_id}: {case.get('description', '')}")
            for e in errors:
                print(f"    {e}")

            results.append({
                "case_id": case_id,
                "status": status,
                "actual": actual,
                "expected": case.get("expected"),
                "errors": errors,
            })
        except Exception as e:
            print(f"[ERR ] {case_id}: {e}")
            failed += 1
            results.append({
                "case_id": case_id,
                "status": "ERROR",
                "error": str(e),
            })

    # Ozet
    total = len(results)
    pass_rate = (total - failed) / max(total, 1)
    print(f"\n=== Sonuc ===")
    print(f"Toplam: {total}")
    print(f"Gecen:  {total - failed}")
    print(f"Kalan:  {failed}")
    print(f"Oran:   %{pass_rate * 100:.1f}")

    # Baseline kaydet
    if args.save_baseline:
        Path(args.baseline_file).parent.mkdir(exist_ok=True)
        with open(args.baseline_file, "w") as f:
            json.dump({
                "weights": args.weights,
                "pass_rate": pass_rate,
                "results": results,
            }, f, indent=2)
        print(f"Baseline kaydedildi: {args.baseline_file}")

    # Baseline ile karsilastir
    if args.compare_baseline and Path(args.baseline_file).exists():
        with open(args.baseline_file, "r") as f:
            baseline = json.load(f)
        baseline_rate = baseline.get("pass_rate", 0)
        delta = pass_rate - baseline_rate
        print(f"\nBaseline pass_rate: %{baseline_rate * 100:.1f}")
        print(f"Delta:              %{delta * 100:+.1f}")

        if delta < -args.fail_threshold:
            print(f"\nREGRESYON: %{abs(delta)*100:.1f} dustuk (esik %{args.fail_threshold*100:.1f})")
            sys.exit(1)

    if failed > 0 and not args.save_baseline:
        # CI ortaminda hata
        if pass_rate < (1 - args.fail_threshold):
            sys.exit(1)


if __name__ == "__main__":
    main()
