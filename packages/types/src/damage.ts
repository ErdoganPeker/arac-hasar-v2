export type DamageType =
  | 'dent'
  | 'scratch'
  | 'crack'
  | 'glass_shatter'
  | 'lamp_broken'
  | 'tire_flat';

export const DAMAGE_TYPE_TR: Record<DamageType, string> = {
  dent: 'Göçük',
  scratch: 'Çizik',
  crack: 'Çatlak',
  glass_shatter: 'Cam kırılması',
  lamp_broken: 'Far kırılması',
  tire_flat: 'Lastik patlağı',
};

export type SeverityLevel = 'hafif' | 'orta' | 'agir';

export const SEVERITY_TR: Record<SeverityLevel, string> = {
  hafif: 'Hafif',
  orta: 'Orta',
  agir: 'Ağır',
};

export interface SeverityResult {
  level: SeverityLevel;
  level_tr: string;
  confidence: number;
  method: 'rule' | 'cnn' | 'ensemble';
}

export interface CostEstimate {
  min_tl: number;
  max_tl: number;
  midpoint_tl?: number;
  confidence: 'high' | 'medium' | 'low';
  source: string;
}

export interface Damage {
  id: number;
  type: DamageType;
  type_tr: string;
  confidence: number;
  severity: SeverityResult;
  bbox: [number, number, number, number];
  polygon_normalized: number[][];
  area_ratio: number;
  cost: CostEstimate;
  is_multi_part: boolean;
  is_low_confidence_match: boolean;
  affected_parts?: string[];
}
