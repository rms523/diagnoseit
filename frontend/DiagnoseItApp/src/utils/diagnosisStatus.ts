import type { Diagnosis } from '../services/api';

/** Queued or being written on the worker; older servers send no status, and theirs are finished. */
export function isDiagnosisRunning(diagnosis: Diagnosis): boolean {
  return diagnosis.status === 'PENDING' || diagnosis.status === 'PROCESSING';
}

function elapsed(since?: string): string {
  const seconds = since ? Math.max(0, Math.round((Date.now() - Date.parse(since)) / 1000)) : NaN;
  if (Number.isNaN(seconds)) return '';
  return seconds < 60 ? ` · ${seconds} s` : ` · ${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

/** "Thinking · 1,240 tokens · 3 min 5 s", from the model's streamed reply. */
export function diagnosisProgressText(diagnosis: Diagnosis): string {
  if (diagnosis.status === 'PENDING') return 'Queued. Starts once any AI review already running has finished.';
  const progress = diagnosis.progress ?? {};
  const time = elapsed(progress.started_at);
  const tokens = (count?: number) => (count ?? 0).toLocaleString();
  if (progress.phase === 'writing') {
    const thought = progress.reasoning_tokens ? `, after ${tokens(progress.reasoning_tokens)} thinking` : '';
    return `Writing the answer · ${tokens(progress.reply_tokens)} tokens${thought}${time}`;
  }
  if (progress.phase === 'thinking') return `Thinking · ${tokens(progress.reasoning_tokens)} tokens${time}`;
  return `Waiting for the model to read the request${time}`;
}
