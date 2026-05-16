import type { Damage } from './damage';

export type PartName =
  | 'front_bumper'
  | 'back_bumper'
  | 'hood'
  | 'front_glass'
  | 'back_glass'
  | 'front_left_door'
  | 'front_right_door'
  | 'back_left_door'
  | 'back_right_door'
  | 'front_left_light'
  | 'front_right_light'
  | 'front_light'
  | 'back_left_light'
  | 'back_right_light'
  | 'back_light'
  | 'left_mirror'
  | 'right_mirror'
  | 'tailgate'
  | 'trunk'
  | 'wheel'
  | 'back_door'
  | 'unknown';

export const PART_TR: Record<PartName, string> = {
  front_bumper: 'Ön tampon',
  back_bumper: 'Arka tampon',
  hood: 'Kaput',
  front_glass: 'Ön cam',
  back_glass: 'Arka cam',
  front_left_door: 'Sol ön kapı',
  front_right_door: 'Sağ ön kapı',
  back_left_door: 'Sol arka kapı',
  back_right_door: 'Sağ arka kapı',
  front_left_light: 'Sol ön far',
  front_right_light: 'Sağ ön far',
  front_light: 'Ön far',
  back_left_light: 'Sol arka stop',
  back_right_light: 'Sağ arka stop',
  back_light: 'Arka stop',
  left_mirror: 'Sol ayna',
  right_mirror: 'Sağ ayna',
  tailgate: 'Bagaj kapağı',
  trunk: 'Bagaj',
  wheel: 'Tekerlek',
  back_door: 'Arka kapı',
  unknown: 'Belirsiz',
};

export type PartStatus =
  | 'clean'
  | 'minor_damage'
  | 'moderate_damage'
  | 'severe_damage';

export const PART_STATUS_TR: Record<PartStatus, string> = {
  clean: 'Hasarsız',
  minor_damage: 'Hafif hasar',
  moderate_damage: 'Orta hasar',
  severe_damage: 'Ağır hasar',
};

export interface Part {
  name: PartName | string;
  name_tr: string;
  confidence: number;
  status: PartStatus;
  damage_count: number;
  polygon_normalized: number[][];
  bbox: [number, number, number, number];
  damages: Damage[];
  part_cost_min_tl: number;
  part_cost_max_tl: number;
  cost_note?: string;
}
