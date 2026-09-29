import type { AIReviewSummary } from '../services/api';

export type ReportParseStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export function isReportParsing(status?: string): boolean {
  return status === 'PENDING' || status === 'PROCESSING';
}

export function statusBadgeClass(status?: string, isParsed?: boolean): string {
  switch (status) {
    case 'COMPLETED':
      return 'badge-success';
    case 'FAILED':
      return 'badge-danger';
    case 'PROCESSING':
    case 'PENDING':
      return 'badge-warning';
    default:
      return isParsed ? 'badge-success' : 'badge-muted';
  }
}

export function statusLabel(status?: string, isParsed?: boolean): string {
  switch (status) {
    case 'COMPLETED':
      return 'Parsed';
    case 'FAILED':
      return 'Failed';
    case 'PROCESSING':
      return 'Processing';
    case 'PENDING':
      return 'Pending';
    default:
      return isParsed ? 'Parsed' : 'Pending';
  }
}

export function testResultBadgeClass(status: string): string {
  switch (status) {
    case 'NORMAL':
      return 'badge-success';
    case 'HIGH':
      return 'badge-danger';
    case 'LOW':
      return 'badge-warning';
    default:
      return 'badge-muted';
  }
}

export type ReportStatusFilter = 'all' | 'parsed' | 'processing' | 'failed';

export function reportMatchesFilter(
  report: { status?: string; is_parsed?: boolean },
  filter: ReportStatusFilter
): boolean {
  if (filter === 'all') return true;
  if (filter === 'processing') return isReportParsing(report.status);
  if (filter === 'failed') return report.status === 'FAILED';
  if (filter === 'parsed') {
    return report.status === 'COMPLETED' ||
      (!!report.is_parsed && report.status !== 'FAILED' && !isReportParsing(report.status));
  }
  return true;
}

/** Badge for a report's AI review in report lists, or null when the report has no review. */
export function aiReviewBadge(summary?: AIReviewSummary): { className: string; label: string; busy: boolean } | null {
  if (!summary) return null;
  switch (summary.status) {
    case 'pending':
      return summary.started
        ? { className: 'badge-info', label: 'AI reviewing', busy: true }
        : { className: 'badge-muted', label: 'AI review queued', busy: false };
    case 'completed':
      return summary.open_suggestions > 0
        ? { className: 'badge-warning', label: `AI: ${summary.open_suggestions} to review`, busy: false }
        : { className: 'badge-success', label: 'AI reviewed', busy: false };
    case 'failed':
      return { className: 'badge-danger', label: 'AI review failed', busy: false };
    default:
      return null;
  }
}
