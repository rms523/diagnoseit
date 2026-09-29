/** Reading the numbers a lab prints, so results can be charted. */

/** Normalize a numeric fragment (may include comma/period thousands or decimal). */
function parseNumericFragment(fragment: string): number | null {
  let t = fragment.trim().replace(/\s/g, '');
  if (!t) return null;

  const lastComma = t.lastIndexOf(',');
  const lastDot = t.lastIndexOf('.');
  if (lastComma !== -1 && lastDot !== -1) {
    if (lastComma > lastDot) {
      t = t.replace(/\./g, '').replace(',', '.');
    } else {
      t = t.replace(/,/g, '');
    }
  } else if (lastComma !== -1) {
    t = t.replace(',', '.');
  }

  const n = parseFloat(t);
  return Number.isFinite(n) ? n : null;
}

/**
 * Parse a lab result value into a number for charting.
 * Handles bounded results (<5, ≥10), units suffixes, and common non-numeric literals.
 */
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

  const s = raw.replace(/≤/g, '<').replace(/≥/g, '>');

  const bounded = s.match(/^[<>]=?\s*([\d.,]+)/);
  if (bounded) return parseNumericFragment(bounded[1]);

  const leading = s.match(/^[+-]?[\d.,]+/);
  if (leading) return parseNumericFragment(leading[0]);

  return null;
}

/** The low and high ends of a printed reference range ("3.5 - 5.1", "between 70 and 100"). */
export function parseRefRangeSpan(ref: string | undefined | null): { min: number; max: number } | null {
  if (!ref?.trim()) return null;
  const s = ref.trim();

  const between = s.match(/between\s*([\d.,]+)\s+and\s+([\d.,]+)/i);
  if (between) {
    const a = parseNumericFragment(between[1]);
    const b = parseNumericFragment(between[2]);
    if (a !== null && b !== null) {
      return { min: Math.min(a, b), max: Math.max(a, b) };
    }
  }

  const dash = s.match(/([\d.,]+)\s*[-–—]\s*([\d.,]+)/);
  if (dash) {
    const a = parseNumericFragment(dash[1]);
    const b = parseNumericFragment(dash[2]);
    if (a !== null && b !== null) {
      return { min: Math.min(a, b), max: Math.max(a, b) };
    }
  }

  const to = s.match(/([\d.,]+)\s+to\s+([\d.,]+)/i);
  if (to) {
    const a = parseNumericFragment(to[1]);
    const b = parseNumericFragment(to[2]);
    if (a !== null && b !== null) {
      return { min: Math.min(a, b), max: Math.max(a, b) };
    }
  }

  return null;
}

/** An axis label with enough decimals for the span it sits in, and no more. */
export function formatAxisTick(v: number, span: number): string {
  if (!Number.isFinite(v)) return '';
  const absSpan = Math.abs(span);
  if (absSpan > 0 && absSpan < 0.01) return v.toExponential(1);
  if (absSpan > 0 && absSpan < 0.5) return v.toFixed(3);
  if (absSpan < 5) return v.toFixed(2);
  if (Math.abs(v) >= 1000) return v.toFixed(0);
  return v.toFixed(1);
}
