/**
 * Client-side CSV / lightweight-PDF builders for inspection data.
 * The CSV is RFC 4180-compatible (quotes-doubled, CRLF). The PDF here is a fallback
 * "text PDF" used when the backend report endpoint is unavailable.
 */
import type { Inspection, InspectionListItem } from '@arac-hasar/types';

function csvEscape(v: unknown): string {
  if (v === null || v === undefined) return '';
  const s = String(v);
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function inspectionsToCsv(items: InspectionListItem[]): string {
  const header = [
    'inspection_id',
    'created_at',
    'status',
    'damage_count',
    'total_cost_midpoint_tl',
  ];
  const rows = items.map((it) => [
    it.inspection_id,
    it.created_at,
    it.status,
    it.damage_count,
    it.total_cost_midpoint_tl ?? '',
  ]);
  return [header, ...rows].map((r) => r.map(csvEscape).join(',')).join('\r\n');
}

export function inspectionDetailToCsv(inspection: Inspection): string {
  const header = [
    'part',
    'part_status',
    'damage_type',
    'severity_level',
    'confidence',
    'cost_min_tl',
    'cost_midpoint_tl',
    'cost_max_tl',
    'area_ratio',
  ];
  const rows: unknown[][] = [];
  for (const part of inspection.parts) {
    if (part.damages.length === 0) {
      rows.push([part.name, part.status, '', '', '', '', '', '', '']);
      continue;
    }
    for (const d of part.damages) {
      rows.push([
        part.name,
        part.status,
        d.type,
        d.severity?.level ?? '',
        d.confidence,
        d.cost?.min_tl ?? '',
        d.cost?.midpoint_tl ?? '',
        d.cost?.max_tl ?? '',
        d.area_ratio,
      ]);
    }
  }
  return [header, ...rows].map((r) => r.map(csvEscape).join(',')).join('\r\n');
}

/**
 * Tiny single-page text PDF builder — used as a graceful fallback when no
 * server-side PDF endpoint is reachable. Real reports come from `api.exportInspectionPdf`.
 */
export function buildTextPdfBase64(title: string, lines: string[]): string {
  const escape = (s: string) =>
    s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
  const body =
    `BT /F1 14 Tf 50 780 Td (${escape(title)}) Tj ET\n` +
    lines
      .map((l, i) => `BT /F1 10 Tf 50 ${750 - i * 14} Td (${escape(l)}) Tj ET`)
      .join('\n');
  const stream = body;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  let pdf = '%PDF-1.4\n';
  const offsets: number[] = [];
  objects.forEach((obj, idx) => {
    offsets.push(pdf.length);
    pdf += `${idx + 1} 0 obj\n${obj}\nendobj\n`;
  });
  const xrefStart = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  offsets.forEach((o) => {
    pdf += `${o.toString().padStart(10, '0')} 00000 n \n`;
  });
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;
  // base64 encode
  let bin = '';
  for (let i = 0; i < pdf.length; i++) bin += String.fromCharCode(pdf.charCodeAt(i) & 0xff);
  return btoa(bin);
}
