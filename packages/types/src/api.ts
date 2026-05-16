import type { Inspection, InspectionStatus } from './inspection';

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'down';
  ml_loaded: boolean;
  timestamp: string;
  version?: string;
}

export interface InspectionCreateResponse {
  inspection_id: string;
  status: InspectionStatus;
  status_url: string;
  created_at: string;
  estimated_completion_seconds?: number;
}

export interface InspectionStatusResponse {
  inspection_id: string;
  status: InspectionStatus;
  result?: Inspection;
  error?: string;
  created_at: string;
  completed_at?: string;
}

export interface SyncInspectionResponse {
  inspection_id: string;
  result: Inspection;
  processed_at: string;
}

export interface ApiError {
  detail: string;
  code?: string;
}

export interface InspectionListItem {
  inspection_id: string;
  created_at: string;
  status: InspectionStatus;
  damage_count: number;
  total_cost_midpoint_tl?: number;
  thumbnail_url?: string;
}

export interface InspectionListResponse {
  items: InspectionListItem[];
  total: number;
  page: number;
  page_size: number;
}
