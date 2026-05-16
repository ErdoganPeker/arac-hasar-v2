"""
backend/models.py
Pydantic v2 semalari — packages/types/src ile birebir senkron.

Onemli: Frontend (web/mobile/desktop) tum tipleri packages/types'tan import eder.
Bu dosyada degisiklik yaptiginda TypeScript tarafini da guncelle.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------- Yardimcilar ----------------

# Tum modeller "ekstra alana izin verme" yi tercih eder — frontend ile sozlesme net olsun
StrictModel = ConfigDict(extra="forbid", populate_by_name=True)
# Bazi durumlar (ML output, ileri uyumluluk) icin esnek model
LooseModel = ConfigDict(extra="allow", populate_by_name=True)


# ---------------- Enum-benzeri Literal'lar (packages/types ile ayni) ----------------

DamageType = Literal[
    "dent",
    "scratch",
    "crack",
    "glass_shatter",
    "lamp_broken",
    "tire_flat",
]

SeverityLevel = Literal["hafif", "orta", "agir"]

CostConfidence = Literal["high", "medium", "low"]

# Pipeline severity classifier 'ensemble_resolved' (rule + CNN ensemble, sonra
# conflict resolution) ve 'rule_based' adlarini da donduruyor; geriye uyumluluk
# icin tum varyantlari kabul ediyoruz.
SeverityMethod = Literal[
    "rule",
    "rule_based",
    "cnn",
    "ensemble",
    "ensemble_resolved",
]

PartName = Literal[
    "front_bumper",
    "back_bumper",
    "hood",
    "front_glass",
    "back_glass",
    "front_left_door",
    "front_right_door",
    "back_left_door",
    "back_right_door",
    "front_left_light",
    "front_right_light",
    "front_light",
    "back_left_light",
    "back_right_light",
    "back_light",
    "left_mirror",
    "right_mirror",
    "tailgate",
    "trunk",
    "wheel",
    "back_door",
    "unknown",
]

PartStatus = Literal["clean", "minor_damage", "moderate_damage", "severe_damage"]

RepairRecommendation = Literal[
    "kucuk_tamir",
    "tamir_boya",
    "parca_degisimi",
    "agir_hasar_pert_degerlendirme",
    "hasar_yok",
]

InspectionStatus = Literal["queued", "processing", "completed", "failed"]


# ---------------- Damage ----------------

class SeverityResult(BaseModel):
    model_config = StrictModel
    level: SeverityLevel
    level_tr: str
    confidence: float = Field(ge=0.0, le=1.0)
    method: SeverityMethod


class CostEstimate(BaseModel):
    model_config = StrictModel
    min_tl: float = Field(ge=0.0)
    max_tl: float = Field(ge=0.0)
    midpoint_tl: Optional[float] = None
    confidence: CostConfidence
    source: str


class Damage(BaseModel):
    """Tek bir hasar kaydi — packages/types/src/damage.ts::Damage ile ayni."""
    model_config = LooseModel  # ML extra alan ekleyebilir (source_image vs)
    id: int
    type: DamageType
    type_tr: str
    confidence: float = Field(ge=0.0, le=1.0)
    severity: SeverityResult
    bbox: Tuple[float, float, float, float]
    polygon_normalized: List[List[float]] = []
    area_ratio: float = Field(ge=0.0, le=1.0)
    cost: CostEstimate
    is_multi_part: bool = False
    is_low_confidence_match: bool = False
    affected_parts: Optional[List[str]] = None


# ---------------- Part ----------------

class Part(BaseModel):
    """Parca-merkezli kayit — packages/types/src/part.ts::Part ile ayni."""
    model_config = LooseModel
    name: str  # PartName veya unbekannt — string union; TS tarafi `PartName | string`
    name_tr: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: PartStatus
    damage_count: int = Field(ge=0)
    polygon_normalized: List[List[float]] = []
    bbox: Tuple[float, float, float, float]
    damages: List[Damage] = []
    part_cost_min_tl: float = Field(default=0.0, ge=0.0)
    part_cost_max_tl: float = Field(default=0.0, ge=0.0)
    cost_note: Optional[str] = None


# ---------------- Inspection ----------------

class InspectionSummary(BaseModel):
    model_config = StrictModel
    total_parts_inspected: int = Field(ge=0)
    damaged_parts_count: int = Field(ge=0)
    clean_parts_count: int = Field(ge=0)
    total_damage_count: int = Field(ge=0)
    unknown_part_damages_count: int = Field(ge=0)
    multi_part_damages_count: int = Field(ge=0)
    most_severe_level: Optional[SeverityLevel] = None
    most_severe_level_tr: Optional[str] = None
    total_damage_area_ratio: float = Field(ge=0.0)
    total_cost_range_tl: Tuple[float, float] = (0.0, 0.0)
    total_cost_midpoint_tl: Optional[float] = None
    cost_confidence: CostConfidence = "low"
    repair_recommendation: RepairRecommendation = "hasar_yok"
    repair_recommendation_tr: str = "Hasar tespit edilmedi"
    estimated_repair_days: int = Field(default=0, ge=0)


class VisualizationUrls(BaseModel):
    model_config = StrictModel
    annotated: Optional[str] = None
    parts: Optional[str] = None
    damages: Optional[str] = None


class InspectionImage(BaseModel):
    model_config = StrictModel
    # ge=0 olarak biraktik: aggregate_results bos sonuc icin (0,0) iskeleti uretebiliyor.
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    url: Optional[str] = None
    hash: Optional[str] = None


class Inspection(BaseModel):
    """Bir incelemenin ana sonuc DTO'su."""
    model_config = LooseModel  # ML 'damages_raw', 'parts_detected' gibi ekstra alan ekleyebilir
    inspection_id: str
    timestamp: str
    image: InspectionImage
    parts: List[Part] = []
    summary: InspectionSummary
    multi_part_damages: Optional[List[Damage]] = None
    unassigned_damages: Optional[List[Damage]] = None
    visualization_urls: Optional[VisualizationUrls] = None


# ---------------- API responses ----------------

class HealthResponse(BaseModel):
    model_config = StrictModel
    status: Literal["ok", "degraded", "down"]
    ml_loaded: bool
    timestamp: str
    version: Optional[str] = None


class VersionResponse(BaseModel):
    model_config = StrictModel
    version: str
    git_sha: str
    build_time: str
    environment: str


class InspectionCreateResponse(BaseModel):
    model_config = StrictModel
    inspection_id: str
    status: InspectionStatus
    status_url: str
    created_at: str
    estimated_completion_seconds: Optional[int] = 30


class InspectionStatusResponse(BaseModel):
    model_config = StrictModel
    inspection_id: str
    status: InspectionStatus
    result: Optional[Inspection] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class SyncInspectionResponse(BaseModel):
    model_config = StrictModel
    inspection_id: str
    result: Inspection
    processed_at: str


class ApiError(BaseModel):
    model_config = StrictModel
    detail: str
    code: Optional[str] = None


class InspectionListItem(BaseModel):
    model_config = StrictModel
    inspection_id: str
    created_at: str
    status: InspectionStatus
    damage_count: int = Field(ge=0)
    total_cost_midpoint_tl: Optional[float] = None
    thumbnail_url: Optional[str] = None


class InspectionListResponse(BaseModel):
    model_config = StrictModel
    items: List[InspectionListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)


# ---------------- Auth ----------------

class UserRegisterRequest(BaseModel):
    model_config = StrictModel
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=120)


class UserLoginRequest(BaseModel):
    model_config = StrictModel
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    model_config = StrictModel
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # access token TTL (sn)


class RefreshTokenRequest(BaseModel):
    model_config = StrictModel
    refresh_token: str = Field(min_length=10)


class UserPublic(BaseModel):
    """Kullaniciya geri donen / /auth/me icin guvenli (PII'siz hash icermez) user kaydi."""
    model_config = StrictModel
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: Literal["user", "admin"] = "user"
    is_active: bool = True
    created_at: str


# ---------------- WebSocket mesajlari ----------------

class WSStatusMessage(BaseModel):
    model_config = StrictModel
    type: Literal["status"] = "status"
    inspection_id: str
    status: InspectionStatus
    progress: Optional[float] = None  # 0.0 - 1.0


class WSCompletedMessage(BaseModel):
    model_config = StrictModel
    type: Literal["completed"] = "completed"
    inspection_id: str
    result: Inspection


class WSErrorMessage(BaseModel):
    model_config = StrictModel
    type: Literal["error"] = "error"
    inspection_id: str
    error: str
