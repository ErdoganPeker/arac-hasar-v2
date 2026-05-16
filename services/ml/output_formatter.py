"""
output_formatter.py - Hasar-merkezli iç JSON'u parça-merkezli son kullanıcı
formatına çevirir + Standart v2 output şeması üretir.

İki ana fonksiyon:
  - to_part_centric(...)        : legacy parts-centric layout (eski clients)
  - build_standard_output(...)  : v2 production şeması (mobile/desktop/web)

V2 standart şema:
{
  "inspection_id": str,
  "image_id": str,
  "timestamp": iso8601,
  "image_size": {"width": int, "height": int},
  "parts":   [Part, ...],
  "damages": [Damage, ...],
  "summary": {
    "total_damage_count": int,
    "dominant_severity": str|null,
    "total_cost_min_tl": float,
    "total_cost_max_tl": float,
    "affected_parts_count": int,
    ...
  },
  "model_versions": {...},
  "processing_ms":  {total, damage, parts, severity, matching, cost},
  "visualization_keys": {annotated, parts_only, damages_only}
}
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from cost_engine import CostEngine, repair_recommendation, estimated_days


# Türkçe çeviri tabloları
PART_TR = {
    "front_bumper": "Ön tampon",
    "back_bumper": "Arka tampon",
    "hood": "Kaput",
    "front_glass": "Ön cam",
    "back_glass": "Arka cam",
    "front_left_door": "Sol ön kapı",
    "front_right_door": "Sağ ön kapı",
    "back_left_door": "Sol arka kapı",
    "back_right_door": "Sağ arka kapı",
    "front_left_light": "Sol ön far",
    "front_right_light": "Sağ ön far",
    "front_light": "Ön far",
    "back_left_light": "Sol arka stop",
    "back_right_light": "Sağ arka stop",
    "back_light": "Arka stop",
    "left_mirror": "Sol ayna",
    "right_mirror": "Sağ ayna",
    "tailgate": "Bagaj kapağı",
    "trunk": "Bagaj",
    "wheel": "Tekerlek",
    "back_door": "Arka kapı",
    "unknown": "Belirsiz",
}

DAMAGE_TYPE_TR = {
    "dent": "Göçük",
    "scratch": "Çizik",
    "crack": "Çatlak",
    "glass_shatter": "Cam kırılması",
    "lamp_broken": "Far kırılması",
    "tire_flat": "Lastik patlağı",
}

SEVERITY_TR = {
    "hafif": "Hafif",
    "orta": "Orta",
    "agir": "Ağır",
}

REPAIR_RECOMMENDATION_TR = {
    "kucuk_tamir": "Küçük tamir yeterli",
    "tamir_boya": "Tamir + boya gerekli",
    "parca_degisimi": "Parça değişimi gerekli",
    "agir_hasar_pert_degerlendirme": "Ağır hasar — pert değerlendirmesi",
    "hasar_yok": "Hasar tespit edilmedi",
}


def to_part_centric(raw_result, damages, parts, total_cost):
    """Iç düzeyde hasar listesi ve parça listesinden parça-merkezli JSON üret.

    Args:
        raw_result: Pipeline'dan çıkan ham JSON (inspection_id, timestamp, image dahil)
        damages: List[DamageRecord]
        parts: List[PartRecord]
        total_cost: CostEstimate veya None

    Returns:
        Parça-merkezli yapıda dict
    """
    # Tespit edilen tüm parçaları bir dict'e koy (status="clean" başlangıçta)
    parts_dict = {}
    for p in parts:
        parts_dict[p.name] = {
            "name": p.name,
            "name_tr": PART_TR.get(p.name, p.name),
            "confidence": round(p.confidence, 4),
            "status": "clean",
            "damage_count": 0,
            "polygon_normalized": [[round(c, 5) for c in pt] for pt in p.polygon_normalized],
            "bbox": [round(x, 2) for x in p.bbox],
            "damages": [],
            "part_cost_min_tl": 0.0,
            "part_cost_max_tl": 0.0,
        }

    # Multi-part hasarlar için ayrı bir kova
    multi_part_damages = []
    unknown_part_damages = []

    # Her hasarı ait olduğu parçaya at
    for d in damages:
        damage_dict = {
            "id": d.id,
            "type": d.type,
            "type_tr": DAMAGE_TYPE_TR.get(d.type, d.type),
            "confidence": round(d.confidence, 4),
            "severity": {
                "level": d.severity.get("level"),
                "level_tr": SEVERITY_TR.get(d.severity.get("level"), d.severity.get("level")),
                "confidence": round(d.severity.get("confidence", 0.0), 4),
                "method": d.severity.get("method"),
            },
            "bbox": [round(x, 2) for x in d.bbox],
            "polygon_normalized": [[round(c, 5) for c in pt] for pt in d.polygon_normalized],
            "area_ratio": round(d.area_ratio, 5),
            "cost": d.cost,
            "is_multi_part": d.is_multi_part,
            "is_low_confidence_match": d.is_low_confidence_match,
        }

        if d.is_multi_part:
            damage_dict["affected_parts"] = (
                [d.primary_part] + [s["part"] for s in d.secondary_parts]
            )
            multi_part_damages.append(damage_dict)

        if d.primary_part == "unknown" or d.primary_part not in parts_dict:
            unknown_part_damages.append(damage_dict)
            continue

        # Ana parçaya ekle
        p_entry = parts_dict[d.primary_part]
        p_entry["damages"].append(damage_dict)
        p_entry["damage_count"] += 1
        p_entry["status"] = _status_from_severities(p_entry["damages"])
        # Parça maliyetini biriktir
        if d.cost:
            p_entry["part_cost_min_tl"] += d.cost.get("min_tl", 0)
            p_entry["part_cost_max_tl"] += d.cost.get("max_tl", 0)

    # Parça maliyetini yuvarlat
    for p_entry in parts_dict.values():
        p_entry["part_cost_min_tl"] = round(p_entry["part_cost_min_tl"], 2)
        p_entry["part_cost_max_tl"] = round(p_entry["part_cost_max_tl"], 2)
        # Aynı parçada birden fazla hasar varsa, parça değişimi gerekecekse
        # naif aggregation yetersiz - en pahalısını al
        if p_entry["damage_count"] > 1 and p_entry["damages"]:
            max_max = max(d["cost"].get("max_tl", 0) for d in p_entry["damages"])
            # Eğer en pahalı tek başına toplamın %70'inden fazlaysa, sadece onu kullan
            # (büyük ihtimal parça değişimi diğerlerini kapsar)
            if max_max > 0.7 * p_entry["part_cost_max_tl"]:
                most_expensive = max(p_entry["damages"], key=lambda x: x["cost"].get("max_tl", 0))
                p_entry["part_cost_min_tl"] = most_expensive["cost"].get("min_tl", 0)
                p_entry["part_cost_max_tl"] = most_expensive["cost"].get("max_tl", 0)
                p_entry["cost_note"] = "Tek parça değişimi diğer hasarları da kapsar"

    # Listeleri sıralı şekilde döndür (önce hasarlı, sonra temiz)
    parts_list = list(parts_dict.values())
    parts_list.sort(key=lambda p: (p["status"] == "clean", -p["damage_count"]))

    # Summary
    damaged_count = sum(1 for p in parts_list if p["status"] != "clean")
    clean_count = sum(1 for p in parts_list if p["status"] == "clean")
    total_damages = sum(p["damage_count"] for p in parts_list) + len(unknown_part_damages)

    most_severe = _aggregate_most_severe(parts_list)
    total_area_ratio = sum(
        d.get("area_ratio", 0)
        for p in parts_list for d in p["damages"]
    )

    summary = {
        "total_parts_inspected": len(parts_list),
        "damaged_parts_count": damaged_count,
        "clean_parts_count": clean_count,
        "total_damage_count": total_damages,
        "unknown_part_damages_count": len(unknown_part_damages),
        "multi_part_damages_count": len(multi_part_damages),
        "most_severe_level": most_severe,
        "most_severe_level_tr": SEVERITY_TR.get(most_severe, most_severe) if most_severe else None,
        "total_damage_area_ratio": round(total_area_ratio, 4),
    }

    if total_cost:
        summary["total_cost_range_tl"] = [
            round(total_cost.min_tl, 2),
            round(total_cost.max_tl, 2),
        ]
        summary["total_cost_midpoint_tl"] = round(total_cost.midpoint, 2)
        summary["cost_confidence"] = total_cost.confidence
        rec = repair_recommendation(total_cost, total_area_ratio)
        summary["repair_recommendation"] = rec
        summary["repair_recommendation_tr"] = REPAIR_RECOMMENDATION_TR.get(rec, rec)
        summary["estimated_repair_days"] = estimated_days(total_cost)
    else:
        summary["total_cost_range_tl"] = [0, 0]
        summary["repair_recommendation"] = "hasar_yok"
        summary["repair_recommendation_tr"] = REPAIR_RECOMMENDATION_TR["hasar_yok"]
        summary["estimated_repair_days"] = 0

    # Final output
    final = {
        "inspection_id": raw_result["inspection_id"],
        "timestamp": raw_result["timestamp"],
        "image": raw_result["image"],
        "parts": parts_list,
        "summary": summary,
    }

    # Edge case'leri saydam göster
    if multi_part_damages:
        final["multi_part_damages"] = multi_part_damages
    if unknown_part_damages:
        final["unassigned_damages"] = unknown_part_damages

    if "visualization_urls" in raw_result:
        final["visualization_urls"] = raw_result["visualization_urls"]

    return final


def _status_from_severities(damages):
    """Parçanın en yüksek şiddet seviyesini durum olarak ata."""
    if not damages:
        return "clean"
    severity_order = {"hafif": 1, "orta": 2, "agir": 3}
    max_sev = max(
        (severity_order.get(d["severity"].get("level"), 0) for d in damages),
        default=0,
    )
    if max_sev == 0:
        return "clean"
    if max_sev == 1:
        return "minor_damage"
    if max_sev == 2:
        return "moderate_damage"
    return "severe_damage"


def _aggregate_most_severe(parts_list):
    """Tüm parçalardaki en yüksek şiddet seviyesini bul."""
    severity_order = {"hafif": 1, "orta": 2, "agir": 3}
    max_sev_value = 0
    max_sev_level = None
    for p in parts_list:
        for d in p["damages"]:
            v = severity_order.get(d["severity"].get("level"), 0)
            if v > max_sev_value:
                max_sev_value = v
                max_sev_level = d["severity"].get("level")
    return max_sev_level


# ---------------------------------------------------------------------------
# V2 standardized output (production schema)
# ---------------------------------------------------------------------------
SEVERITY_RANK = {"hafif": 1, "orta": 2, "agir": 3}


def _xyxy_to_xywh(bbox) -> List[float]:
    x1, y1, x2, y2 = bbox
    return [round(float(x1), 2), round(float(y1), 2),
            round(float(x2 - x1), 2), round(float(y2 - y1), 2)]


def _polygon_to_pixels(d_or_p, width: int, height: int) -> List[List[float]]:
    """Prefer stored polygon_pixels; fall back to denormalising polygon_normalized."""
    pixels = getattr(d_or_p, "polygon_pixels", None)
    if pixels:
        return [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in pixels]
    norm = getattr(d_or_p, "polygon_normalized", None) or []
    return [[round(float(p[0]) * width, 2), round(float(p[1]) * height, 2)] for p in norm]


def _cost_summary_from_damage(damage_cost: dict) -> Dict[str, Any]:
    if not damage_cost:
        return {"min_tl": 0.0, "max_tl": 0.0, "range_label": "0 TL"}
    min_tl = float(damage_cost.get("min_tl", 0.0))
    max_tl = float(damage_cost.get("max_tl", 0.0))
    label = f"{min_tl:.0f} - {max_tl:.0f} TL"
    return {
        "min_tl": round(min_tl, 2),
        "max_tl": round(max_tl, 2),
        "midpoint_tl": round((min_tl + max_tl) / 2, 2),
        "range_label": label,
        "confidence": damage_cost.get("confidence", "low"),
        "source": damage_cost.get("source"),
    }


def _dominant_severity(damages) -> Optional[str]:
    best_rank = 0
    best = None
    for d in damages:
        lvl = d.severity.get("level") if isinstance(d.severity, dict) else None
        r = SEVERITY_RANK.get(lvl, 0)
        if r > best_rank:
            best_rank = r
            best = lvl
    return best


def build_standard_output(*,
                          inspection_id: str,
                          image_id: str,
                          image_size: Tuple[int, int],
                          damages,
                          parts,
                          total_cost,
                          timings_ms: Dict[str, float],
                          model_versions: Dict[str, str],
                          visualization_keys: Optional[Dict[str, str]] = None,
                          timestamp: Optional[str] = None) -> Dict[str, Any]:
    """Build the v2 standardized JSON output (production schema).

    Inputs are the internal DamageRecord/PartRecord lists from pipeline.py.
    Returns a serialisable dict.
    """
    width, height = image_size
    visualization_keys = visualization_keys or {}

    # ---- Parts ----------------------------------------------------------
    parts_out: List[Dict[str, Any]] = []
    for p in parts:
        parts_out.append({
            "id": int(p.id),
            "name": p.name,
            "name_tr": PART_TR.get(p.name, p.name),
            "confidence": round(float(p.confidence), 4),
            "bbox": _xyxy_to_xywh(p.bbox),
            "polygon": _polygon_to_pixels(p, width, height),
            "polygon_normalized": [[round(float(c), 5) for c in pt]
                                    for pt in (p.polygon_normalized or [])],
            "damages": list(p.damages),
        })

    # ---- Damages --------------------------------------------------------
    damages_out: List[Dict[str, Any]] = []
    for d in damages:
        sev_level = d.severity.get("level") if isinstance(d.severity, dict) else None
        damages_out.append({
            "id": int(d.id),
            "type": d.type,
            "type_tr": DAMAGE_TYPE_TR.get(d.type, d.type),
            "primary_part": d.primary_part,
            "primary_part_tr": PART_TR.get(d.primary_part, d.primary_part),
            "secondary_parts": [
                {"name": s["part"],
                 "name_tr": PART_TR.get(s["part"], s["part"]),
                 "intersection_ratio": round(float(s.get("intersection_ratio", 0.0)), 4),
                 "iou": round(float(s.get("iou", 0.0)), 4)}
                for s in (d.secondary_parts or [])
            ],
            "bbox": _xyxy_to_xywh(d.bbox),
            "polygon": _polygon_to_pixels(d, width, height),
            "polygon_normalized": [[round(float(c), 5) for c in pt]
                                    for pt in (d.polygon_normalized or [])],
            "area_ratio": round(float(d.area_ratio), 5),
            "confidence": round(float(d.confidence), 4),
            "severity": {
                "label": sev_level,
                "label_tr": SEVERITY_TR.get(sev_level, sev_level) if sev_level else None,
                "confidence": round(float(d.severity.get("confidence", 0.0))
                                      if isinstance(d.severity, dict) else 0.0, 4),
                "method": d.severity.get("method") if isinstance(d.severity, dict) else None,
            },
            "cost": _cost_summary_from_damage(d.cost),
            "is_multi_part": bool(d.is_multi_part),
            "is_low_confidence_match": bool(d.is_low_confidence_match),
        })

    # ---- Summary --------------------------------------------------------
    affected = {d.primary_part for d in damages
                if d.primary_part and d.primary_part != "unknown"}
    dominant = _dominant_severity(damages)

    total_min = round(float(total_cost.min_tl), 2) if total_cost else 0.0
    total_max = round(float(total_cost.max_tl), 2) if total_cost else 0.0
    total_area = sum(float(d.area_ratio) for d in damages)
    rec = repair_recommendation(total_cost, total_area) if total_cost else "hasar_yok"
    days = estimated_days(total_cost) if total_cost else 0

    summary = {
        "total_damage_count": len(damages_out),
        "dominant_severity": dominant,
        "dominant_severity_tr": SEVERITY_TR.get(dominant, dominant) if dominant else None,
        "total_cost_min_tl": total_min,
        "total_cost_max_tl": total_max,
        "total_cost_midpoint_tl": round((total_min + total_max) / 2, 2),
        "affected_parts_count": len(affected),
        "detected_parts_count": len(parts_out),
        "multi_part_damage_count": sum(1 for d in damages if d.is_multi_part),
        "unassigned_damage_count": sum(1 for d in damages if d.primary_part == "unknown"),
        "low_confidence_match_count": sum(1 for d in damages if d.is_low_confidence_match),
        "total_damage_area_ratio": round(total_area, 5),
        "repair_recommendation": rec,
        "repair_recommendation_tr": REPAIR_RECOMMENDATION_TR.get(rec, rec),
        "estimated_repair_days": days,
    }

    # ---- Processing ms (round) -----------------------------------------
    pm = {k: round(float(v), 2) for k, v in (timings_ms or {}).items()}

    # ---- Visualization keys (storage hints; backend fills real URLs) ---
    vk = {
        "annotated": visualization_keys.get("annotated"),
        "parts_only": visualization_keys.get("parts_only"),
        "damages_only": visualization_keys.get("damages_only"),
    }

    return {
        "inspection_id": inspection_id,
        "image_id": image_id,
        "timestamp": timestamp,
        "image_size": {"width": int(width), "height": int(height)},
        "parts": parts_out,
        "damages": damages_out,
        "summary": summary,
        "model_versions": dict(model_versions),
        "processing_ms": pm,
        "visualization_keys": vk,
    }
