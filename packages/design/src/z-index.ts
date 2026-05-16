/**
 * Z-index scale — ensures consistent layering across all UI surfaces.
 */

export const zIndex = {
  base: 0,
  raised: 10,
  dropdown: 100,
  sticky: 200,
  overlay: 300,
  modal: 400,
  popover: 500,
  toast: 600,
  tooltip: 700,
  loader: 800,
} as const;

export type ZIndexToken = keyof typeof zIndex;
