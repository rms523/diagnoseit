/** Readable message from an ApiService error ("API Error: 400 Bad Request - {json body}"). */
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback;
  const body = err.message.replace(/^API Error: \d+[^-]*- /, '').trim();
  try {
    const data: unknown = JSON.parse(body);
    if (data && typeof data === 'object') {
      const record = data as Record<string, unknown>;
      if (typeof record.error === 'string') return record.error;
      if (typeof record.detail === 'string') return record.detail;
      const [field, value] = Object.entries(record)[0] ?? [];
      if (field) {
        const text = Array.isArray(value) ? value.join(' ') : String(value);
        return field === 'non_field_errors' ? text : `${field.replace(/_/g, ' ')}: ${text}`;
      }
    }
  } catch {
    /* body is not JSON */
  }
  return body || fallback;
}
