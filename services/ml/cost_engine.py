"""
cost_engine.py
Hasar tipi + parca + siddet kombinasyonunu maliyet araligina cevirir.

Strateji:
  1. cost_table.yaml'da spesifik kombinasyon varsa onu kullan
  2. Yoksa varsayilan parca + siddet kombinasyonuna geri don
  3. O da yoksa son care: hasar tipi ortalamasi

Tum fiyatlar Turk Lirasi (TL) cinsinden.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import yaml


logger = logging.getLogger(__name__)

# Son care default - hicbir lookup tutmazsa
HARD_DEFAULTS = {
    "hafif": (300, 1500),
    "orta": (1500, 5000),
    "agir": (5000, 20000),
}


@dataclass
class CostEstimate:
    min_tl: float
    max_tl: float
    confidence: str    # "high", "medium", "low" - lookup kalitesine gore
    source: str        # Hangi kuraldan geldi (debug)

    @property
    def midpoint(self):
        return (self.min_tl + self.max_tl) / 2

    def to_dict(self):
        return {
            "min_tl": round(self.min_tl, 2),
            "max_tl": round(self.max_tl, 2),
            "midpoint_tl": round(self.midpoint, 2),
            "confidence": self.confidence,
            "source": self.source,
        }


class CostEngine:
    def __init__(self, cost_table_path="cost_table.yaml"):
        self.path = self._resolve_path(Path(cost_table_path))
        if not self.path.exists():
            logger.warning(
                "cost_table.yaml bulunamadi (denenen yollar: configured=%s, "
                "module_dir=%s, cwd=%s) -- sadece hard defaults kullanilacak",
                cost_table_path,
                Path(__file__).resolve().parent / "cost_table.yaml",
                Path.cwd() / "cost_table.yaml",
            )
            self.table = {}
        else:
            with open(self.path, "r", encoding="utf-8") as f:
                self.table = yaml.safe_load(f) or {}
            logger.info("cost_table.yaml yuklendi: %s (%d top-level entry)",
                        self.path, len(self.table) if isinstance(self.table, dict) else 0)

    @staticmethod
    def _resolve_path(p: Path) -> Path:
        """Resolve cost_table path with fallbacks.

        Tries, in order:
          1. The path as configured (absolute or relative to cwd).
          2. The same basename next to this module (services/ml/<basename>).
          3. The basename in the current working directory.
        Returns the first one that exists, or the original configured path
        if none exist (caller logs a warning).
        """
        try:
            if p.exists():
                return p
            module_local = Path(__file__).resolve().parent / p.name
            if module_local.exists():
                return module_local
            cwd_local = Path.cwd() / p.name
            if cwd_local.exists():
                return cwd_local
        except Exception:  # noqa: BLE001
            pass
        return p

    def estimate(self, part, damage_type, severity) -> CostEstimate:
        """Tek bir hasar icin maliyet tahmini."""
        # 1. Spesifik kombinasyon
        try:
            rng = self.table[part][damage_type][severity]
            return CostEstimate(
                min_tl=float(rng[0]),
                max_tl=float(rng[1]),
                confidence="high",
                source=f"{part}.{damage_type}.{severity}",
            )
        except (KeyError, TypeError, IndexError):
            pass

        # 2. Parca defaults
        try:
            rng = self.table[part]["default"][severity]
            return CostEstimate(
                min_tl=float(rng[0]),
                max_tl=float(rng[1]),
                confidence="medium",
                source=f"{part}.default.{severity}",
            )
        except (KeyError, TypeError, IndexError):
            pass

        # 3. Hasar tipi defaults
        try:
            rng = self.table["_global"][damage_type][severity]
            return CostEstimate(
                min_tl=float(rng[0]),
                max_tl=float(rng[1]),
                confidence="low",
                source=f"_global.{damage_type}.{severity}",
            )
        except (KeyError, TypeError, IndexError):
            pass

        # 4. Hard default
        rng = HARD_DEFAULTS.get(severity, (1000, 5000))
        logger.info(f"Hard default kullanildi: ({part}, {damage_type}, {severity})")
        return CostEstimate(
            min_tl=float(rng[0]),
            max_tl=float(rng[1]),
            confidence="low",
            source="hard_default",
        )

    def aggregate(self, estimates):
        """Coklu hasarin toplam maliyet araligi.

        Not: Naif toplam yapariz; pratikte parca degisikligi overlap'i olabilir.
        v2'de smart aggregation (ayni parca icin sadece en agir).
        """
        if not estimates:
            return CostEstimate(0, 0, "high", "no_damage")

        # Ayni parcanin coklu hasari icinde en pahaliyi al (parca degisirse her sey ucar)
        by_part = {}
        for est_info in estimates:
            part = est_info["part"]
            est = est_info["estimate"]
            if part not in by_part or est.max_tl > by_part[part].max_tl:
                by_part[part] = est

        total_min = sum(e.min_tl for e in by_part.values())
        total_max = sum(e.max_tl for e in by_part.values())

        # Multi-damage indirimi - 2'den fazlasinda %5-10 indirim
        if len(by_part) >= 3:
            total_min *= 0.92
            total_max *= 0.95

        return CostEstimate(
            min_tl=total_min,
            max_tl=total_max,
            confidence="medium",  # Aggregation belirsizlik ekler
            source=f"aggregate_{len(by_part)}_parts",
        )


def repair_recommendation(estimate, total_damage_area_ratio):
    """Onarim onerisi: tamir / parca degisimi / pert."""
    if estimate.midpoint < 2000:
        return "kucuk_tamir"
    elif estimate.midpoint < 10000:
        return "tamir_boya"
    elif estimate.midpoint < 30000 or total_damage_area_ratio < 0.15:
        return "parca_degisimi"
    else:
        return "agir_hasar_pert_degerlendirme"


def estimated_days(estimate):
    """Yaklasik onarim suresi (gun)."""
    if estimate.midpoint < 1000:
        return 1
    elif estimate.midpoint < 5000:
        return 2
    elif estimate.midpoint < 15000:
        return 4
    else:
        return 7


if __name__ == "__main__":
    # CLI test
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cost_table", default="cost_table.yaml")
    p.add_argument("--part", required=True)
    p.add_argument("--damage_type", required=True)
    p.add_argument("--severity", choices=["hafif", "orta", "agir"], required=True)
    args = p.parse_args()

    engine = CostEngine(args.cost_table)
    est = engine.estimate(args.part, args.damage_type, args.severity)
    print(f"Tahmini maliyet: {est.min_tl:.0f} - {est.max_tl:.0f} TL")
    print(f"Guven: {est.confidence}")
    print(f"Kaynak: {est.source}")
