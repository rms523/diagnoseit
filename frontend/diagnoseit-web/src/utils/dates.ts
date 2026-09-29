const MONTH_NAMES = [
  'january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december',
];

function monthNumber(name: string): number | null {
  const key = name.toLowerCase();
  const index = MONTH_NAMES.findIndex(month => key.length >= 3 && month.startsWith(key));
  return index === -1 ? null : index + 1;
}

function toIsoDate(year: number, month: number, day: number): string | null {
  if (month < 1 || month > 12 || day < 1 || day > new Date(year, month, 0).getDate()) {
    return null;
  }
  return [
    String(year).padStart(4, '0'),
    String(month).padStart(2, '0'),
    String(day).padStart(2, '0'),
  ].join('-');
}

/** A date as YYYY-MM-DDTHH:mm in the viewer's time zone: the value format of <input type="datetime-local">. */
export function toDateTimeLocalValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** An <input type="datetime-local"> value, read in the viewer's time zone, as an ISO timestamp; null if invalid. */
export function dateTimeLocalToIso(value: string): string | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

const TIME_SUFFIX_RE = /[ T](\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?\s*(am|pm)?$/i;

/**
 * Normalize a typed or pasted date with an optional time to "YYYY-MM-DD" or "YYYY-MM-DD HH:mm".
 *
 * The date accepts every format parseDateInput does; the time may be 24-hour (09:30, 18:05) or
 * 12-hour (9:30 AM, 06:05PM). Returns null when the date or time is not real.
 */
export function parseDateTimeInput(raw: string): string | null {
  const text = raw.trim().replace(/\s+/g, ' ');
  const date = parseDateInput(text);
  if (!date) return null;
  const match = text.match(TIME_SUFFIX_RE);
  if (!match) return date;

  let hours = Number(match[1]);
  const minutes = Number(match[2]);
  const meridiem = match[3]?.toLowerCase();
  if (minutes > 59) return null;
  if (meridiem) {
    if (hours < 1 || hours > 12) return null;
    hours = (hours % 12) + (meridiem === 'pm' ? 12 : 0);
  } else if (hours > 23) {
    return null;
  }
  return `${date} ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

/** A typed date with an optional time, read in the viewer's time zone (midnight if no time), as an ISO timestamp. */
export function dateTimeTextToIso(raw: string): string | null {
  const normalized = parseDateTimeInput(raw);
  if (!normalized) return null;
  const [date, time = '00:00'] = normalized.split(' ');
  return dateTimeLocalToIso(`${date}T${time}`);
}

/** A date as "YYYY-MM-DD HH:mm" in the viewer's time zone, the text form parseDateTimeInput produces. */
export function toDateTimeText(date: Date): string {
  return toDateTimeLocalValue(date).replace('T', ' ');
}

/** Today's date as YYYY-MM-DD in the viewer's time zone (toISOString would give the UTC date). */
export function todayIsoDate(): string {
  const now = new Date();
  return toIsoDate(now.getFullYear(), now.getMonth() + 1, now.getDate()) ?? '';
}

/**
 * Normalize a typed or pasted date to YYYY-MM-DD, or return null if it is not a real date.
 *
 * Accepts 2026-05-14, 2026/05/14, 14/05/2026, 14-05-2026, 14.05.2026, 14 May 2026,
 * 14-May-2026, 14/May/2026, and May 14, 2026, optionally followed by a time as printed on
 * lab reports ("08/Jul/2026 10:22AM"). Numeric dates are read day-first, as Indian labs
 * print them, unless only month-first is a valid date (05/14/2026).
 */
export function parseDateInput(raw: string): string | null {
  const text = raw
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/[ T]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?\s*(am|pm)?\s*(z|[+-]\d{2}:?\d{2})?$/i, '');

  let match = text.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/);
  if (match) {
    return toIsoDate(Number(match[1]), Number(match[2]), Number(match[3]));
  }

  match = text.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/);
  if (match) {
    const [first, second, year] = [Number(match[1]), Number(match[2]), Number(match[3])];
    return toIsoDate(year, second, first) ?? toIsoDate(year, first, second);
  }

  match = text.match(/^(\d{1,2})[-/. ]([a-z]{3,9})\.?[-/., ]+(\d{4})$/i);
  if (match) {
    const month = monthNumber(match[2]);
    return month ? toIsoDate(Number(match[3]), month, Number(match[1])) : null;
  }

  match = text.match(/^([a-z]{3,9})\.? (\d{1,2}),? (\d{4})$/i);
  if (match) {
    const month = monthNumber(match[1]);
    return month ? toIsoDate(Number(match[3]), month, Number(match[2])) : null;
  }

  return null;
}
