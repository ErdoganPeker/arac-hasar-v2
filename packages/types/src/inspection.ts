import type { Damage } from './damage';
import type { Part } from './part';
import type { SeverityLevel } from './damage';

export type RepairRecommendation =
  | 'kucuk_tamir'
  | 'tamir_boya'
  | 'parca_degisimi'
  | 'agir_hasar_pert_degerlendirme'
  | 'hasar_yok';

export const REPAIR_RECOMMENDATION_TR: Record<RepairRecommendation, string> = {
  kucuk_tamir: 'Küçük tamir yeterli',
  tamir_boya: 'Tamir + boya gerekli',
  parca_degisimi: 'Parça değişimi gerekli',
  agir_hasar_pert_degerlendirme: 'Ağır hasar — pert değerlendirmesi',
  hasar_yok: 'Hasar tespit edilmedi',
};

export interface InspectionSummary {
  total_parts_inspected: number;
  damaged_parts_count: number;
  clean_parts_count: number;
  total_damage_count: number;
  unknown_part_damages_count: number;
  multi_part_damages_count: number;
  most_severe_level: SeverityLevel | null;
  most_severe_level_tr: string | null;
  total_damage_area_ratio: number;
  total_cost_range_tl: [number, number];
  total_cost_midpoint_tl?: number;
  cost_confidence: 'high' | 'medium' | 'low';
  repair_recommendation: RepairRecommendation;
  repair_recommendation_tr: string;
  estimated_repair_days: number;
}

export interface VisualizationUrls {
  annotated?: string;
  parts?: string;
  damages?: string;
}

export interface InspectionImage {
  width: number;
  height: number;
  url?: string;
  hash?: string;
}

export interface Inspection {
  inspection_id: string;
  timestamp: string;
  image: InspectionImage;
  parts: Part[];
  summary: InspectionSummary;
  multi_part_damages?: Damage[];
  unassigned_damages?: Damage[];
  visualization_urls?: VisualizationUrls;
}

export type InspectionStatus = 'queued' | 'processing' | 'completed' | 'failed';
