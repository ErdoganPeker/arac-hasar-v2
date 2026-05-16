"""
visualization.py — Zengin görsel overlay üretimi.

Her inspection için 3 PNG dosyası üretir:
  1. annotated.jpg   — ana sonuç (parça yarı saydam + hasar bbox/polygon)
  2. parts.png       — sadece parça segmentasyonu
  3. damages.png     — sadece hasar mask'ları (şiddete göre renk kodlu)

Kullanim:
    from visualization import render_all
    paths = render_all(image, damages, parts, output_dir="./visuals",
                       inspection_id="abc123")
"""
import hashlib
import logging
from pathlib import Path

import cv2
import numpy as np


logger = logging.getLogger(__name__)


# Hasar şiddet renkleri (BGR formatında - OpenCV)
SEVERITY_COLORS_BGR = {
    "hafif": (129, 199, 132),    # yeşil
    "orta": (51, 153, 255),       # turuncu/amber
    "agir": (51, 51, 239),        # kırmızı
    None: (180, 180, 180),        # gri
}

# Parça için deterministik renkler (hash'ten)
def part_color_bgr(part_name):
    """Parça adından deterministik BGR renk üret."""
    h = hashlib.md5(part_name.encode()).digest()
    # 0-255 arası 3 byte → BGR
    return (int(h[0]) % 200 + 55, int(h[1]) % 200 + 55, int(h[2]) % 200 + 55)


def severity_color(sev_level):
    """Şiddet seviyesinden BGR renk."""
    return SEVERITY_COLORS_BGR.get(sev_level, SEVERITY_COLORS_BGR[None])


def overlay_mask(image, mask, color, alpha=0.4):
    """Bir mask'ı görüntü üzerine yarı saydam overlay'le."""
    if mask is None or mask.sum() == 0:
        return image
    overlay = image.copy()
    overlay[mask > 0] = color
    return cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0)


def draw_polygon(image, polygon, color, thickness=2, fill_alpha=0.0):
    """Polygon çiz. fill_alpha > 0 ise dolu da."""
    if polygon is None or len(polygon) < 3:
        return image
    pts = np.array(polygon, dtype=np.int32).reshape((-1, 2))

    if fill_alpha > 0:
        overlay = image.copy()
        cv2.fillPoly(overlay, [pts], color)
        image = cv2.addWeighted(overlay, fill_alpha, image, 1 - fill_alpha, 0)

    cv2.polylines(image, [pts], isClosed=True, color=color, thickness=thickness)
    return image


def draw_bbox(image, bbox, color, thickness=2, dashed=False):
    """Bounding box çiz, opsiyonel dashed."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    if not dashed:
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    else:
        _draw_dashed_rect(image, (x1, y1), (x2, y2), color, thickness)
    return image


def _draw_dashed_rect(image, p1, p2, color, thickness):
    """Kesik çizgili dikdörtgen."""
    x1, y1 = p1
    x2, y2 = p2
    dash_len = 8
    # Üst
    for x in range(x1, x2, dash_len * 2):
        cv2.line(image, (x, y1), (min(x + dash_len, x2), y1), color, thickness)
    # Alt
    for x in range(x1, x2, dash_len * 2):
        cv2.line(image, (x, y2), (min(x + dash_len, x2), y2), color, thickness)
    # Sol
    for y in range(y1, y2, dash_len * 2):
        cv2.line(image, (x1, y), (x1, min(y + dash_len, y2)), color, thickness)
    # Sağ
    for y in range(y1, y2, dash_len * 2):
        cv2.line(image, (x2, y), (x2, min(y + dash_len, y2)), color, thickness)


def draw_label(image, text, position, bg_color, text_color=(255, 255, 255),
               font_scale=0.5, thickness=1):
    """Etiket çiz - arka plan + yazı."""
    x, y = position
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    pad = 4
    # Arka plan
    cv2.rectangle(
        image,
        (x, y - th - pad * 2),
        (x + tw + pad * 2, y),
        bg_color,
        -1,
    )
    # Yazı
    cv2.putText(
        image, text, (x + pad, y - pad),
        font, font_scale, text_color, thickness, cv2.LINE_AA,
    )
    return image


def render_annotated(image, damages, parts):
    """Ana sonuç görseli — parça mask'ları + hasar bbox + polygon."""
    result = image.copy()

    # 1. Parça maskelerini soluk overlay'le
    for p in parts:
        if p.mask is not None:
            color = part_color_bgr(p.name)
            result = overlay_mask(result, p.mask, color, alpha=0.12)

    # 2. Hasarları üzerine ekle (şiddete göre renk)
    for d in damages:
        sev_level = d.severity.get("level") if isinstance(d.severity, dict) else None
        color = severity_color(sev_level)

        # Polygon dolu + stroke
        if d.polygon_normalized:
            h, w = image.shape[:2]
            poly_px = [(p[0] * w, p[1] * h) for p in d.polygon_normalized]
            result = draw_polygon(result, poly_px, color, thickness=2, fill_alpha=0.35)

        # Bbox dashed
        if d.bbox:
            result = draw_bbox(result, d.bbox, color, thickness=1, dashed=True)

        # Etiket
        x1, y1, _, _ = [int(v) for v in d.bbox]
        sev_tr = {"hafif": "Hafif", "orta": "Orta", "agir": "Agir"}.get(sev_level, "?")
        label = f"{d.type} • {sev_tr}"
        result = draw_label(result, label, (x1, max(y1, 20)), color)

    return result


def render_parts_only(image, parts):
    """Sadece parça segmentasyonu — her parça farklı renk."""
    result = image.copy()
    for p in parts:
        if p.mask is None:
            continue
        color = part_color_bgr(p.name)
        result = overlay_mask(result, p.mask, color, alpha=0.45)

        # Etiket: parçanın merkezi
        ys, xs = np.where(p.mask > 0)
        if len(xs) > 0:
            cx, cy = int(np.mean(xs)), int(np.mean(ys))
            result = draw_label(result, p.name, (cx, cy), color)
    return result


def render_damages_only(image, damages):
    """Sadece hasar overlay — şiddete göre renk kodlu."""
    # Karartılmış arka plan (hasarları öne çıkar)
    result = cv2.addWeighted(image, 0.3, np.zeros_like(image), 0.7, 0)

    for d in damages:
        sev_level = d.severity.get("level") if isinstance(d.severity, dict) else None
        color = severity_color(sev_level)

        # Mask varsa dolu
        if d.mask is not None and d.mask.sum() > 0:
            result = overlay_mask(result, d.mask, color, alpha=0.65)

        # Bbox + etiket
        if d.bbox:
            result = draw_bbox(result, d.bbox, color, thickness=2)
            x1, y1, _, _ = [int(v) for v in d.bbox]
            sev_tr = {"hafif": "Hafif", "orta": "Orta", "agir": "Agir"}.get(sev_level, "?")
            label = f"{d.type} • {sev_tr}"
            result = draw_label(result, label, (x1, max(y1, 20)), color)

    return result


def render_all(image, damages, parts, output_dir, inspection_id):
    """Üç ayrı görsel üret ve dosya yollarını döndür."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    paths = {}

    try:
        annotated = render_annotated(image, damages, parts)
        p1 = out / f"{inspection_id}_annotated.jpg"
        cv2.imwrite(str(p1), annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
        paths["annotated_image"] = str(p1)
    except Exception as e:
        logger.error(f"annotated render hatası: {e}")

    try:
        parts_img = render_parts_only(image, parts)
        p2 = out / f"{inspection_id}_parts.png"
        cv2.imwrite(str(p2), parts_img)
        paths["parts_overlay"] = str(p2)
    except Exception as e:
        logger.error(f"parts render hatası: {e}")

    try:
        damages_img = render_damages_only(image, damages)
        p3 = out / f"{inspection_id}_damages.png"
        cv2.imwrite(str(p3), damages_img)
        paths["damages_overlay"] = str(p3)
    except Exception as e:
        logger.error(f"damages render hatası: {e}")

    return paths


if __name__ == "__main__":
    # CLI test
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output_dir", default="./visuals")
    parser.add_argument("--damage_weights", required=True)
    parser.add_argument("--parts_weights", required=True)
    args = parser.parse_args()

    from pipeline import DamagePipelineV2

    pipe = DamagePipelineV2(
        damage_weights=args.damage_weights,
        parts_weights=args.parts_weights,
    )
    image = cv2.imread(args.image)
    damages = pipe._detect_damages(image)
    parts = pipe._detect_parts(image)
    if damages and parts:
        pipe._assign_parts_to_damages(damages, parts)
    if damages:
        pipe._classify_severities(damages, image)

    paths = render_all(image, damages, parts, args.output_dir, "test")
    print("Üretildi:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
