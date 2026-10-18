import type { DuplicateReport } from '../services/api';

/** The report an upload repeats, when the API refused the file as already uploaded (409, duplicate_file). */
export function duplicateUploadOf(err: unknown): DuplicateReport | null {
  if (!(err instanceof Error) || !/^API Error: 409\b/.test(err.message)) return null;
  try {
    const data = JSON.parse(err.message.replace(/^API Error: \d+[^-]*- /, ''));
    return data?.code === 'duplicate_file' && data.duplicate_of ? (data.duplicate_of as DuplicateReport) : null;
  } catch {
    return null;
  }
}
