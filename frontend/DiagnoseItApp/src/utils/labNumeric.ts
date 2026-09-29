export interface TrendPointInput {
  date: string;
  value: string;
  unit: string;
  status: string;
  reference_range: string;
}

function parseNumericFragment(fragment: string): number | null {
  let t = fragment.trim().replace(/\s/g, '');
  if (!t) return null;

  const lastComma = t.lastIndexOf(',');
  const lastDot = t.lastIndexOf('.');
  if (lastComma !== -1 && lastDot !== -1) {
    t = lastComma > lastDot ? t.replace(/\./g, '').replace(',', '.') : t.replace(/,/g, '');
  } else if (lastComma !== -1) {
    t = t.replace(',', '.');
  }

  const n = parseFloat(t);
  return Number.isFinite(n) ? n : null;
}

export function parseLabNumeric(value: string | undefined | null): number | null {
  if (value == null) return null;
  const raw = String(value).trim();
  if (!raw) return null;

  const lower = raw.toLowerCase();
  const nonNumeric = new Set([
    'negative', 'positive', 'trace', 'reactive', 'non-reactive', 'nonreactive',
    'n/a', 'na', 'pending', 'tnp', 'see note', 'see comment', 'see below',
    'nil', 'none', 'not detected', 'undetectable',
  ]);
  if (nonNumeric.has(lower)) return null;

  let s = raw.replace(/≤/g, '<').replace(/≥/g, '>');

  const bound = s.match(/^(?:<=|>=|<|>)\s*(-?[\d.,]+(?:[eE][+-]?\d+)?)/);
  if (bound) return parseNumericFragment(bound[1]);

  if (/^\d+\s*:\s*\d+$/.test(s.replace(/\s/g, ''))) return null;

  const numMatch = s.match(/-?[\d.,]+(?:[eE][+-]?\d+)?/);
  if (!numMatch) return null;
  return parseNumericFragment(numMatch[0]);
}

export function parseRefRangeSpan(ref: string | undefined | null): { min: number; max: number } | null {
  if (!ref?.trim()) return null;
  const s = ref.trim();

  const between = s.match(/between\s*([\d.,]+)\s+and\s+([\d.,]+)/i);
  if (between) {
    const a = parseNumericFragment(between[1]);
    const b = parseNumericFragment(between[2]);
    if (a !== null && b !== null) return { min: Math.min(a, b), max: Math.max(a, b) };
  }

  const dash = s.match(/([\d.,]+)\s*[-–—]\s*([\d.,]+)/);
  if (dash) {
    const a = parseNumericFragment(dash[1]);
    const b = parseNumericFragment(dash[2]);
    if (a !== null && b !== null) return { min: Math.min(a, b), max: Math.max(a, b) };
  }

  const to = s.match(/([\d.,]+)\s+to\s+([\d.,]+)/i);
  if (to) {
    const a = parseNumericFragment(to[1]);
    const b = parseNumericFragment(to[2]);
    if (a !== null && b !== null) return { min: Math.min(a, b), max: Math.max(a, b) };
  }

  return null;
}

export function formatAxisTick(v: number, span: number): string {
  if (!Number.isFinite(v)) return '';
  const absSpan = Math.abs(span);
  if (absSpan > 0 && absSpan < 0.01) return v.toExponential(1);
  if (absSpan > 0 && absSpan < 0.5) return v.toFixed(3);
  if (absSpan < 5) return v.toFixed(2);
  if (Math.abs(v) >= 1000) return v.toFixed(0);
  return v.toFixed(1);
}

export function buildPlottablePoints(trends: TrendPointInput[]) {
  return trends
    .map(t => {
      const val = parseLabNumeric(t.value);
      if (val === null) return null;
      return { val, date: t.date, status: t.status, refRange: t.reference_range };
    })
    .filter((p): p is NonNullable<typeof p> => p !== null);
}
