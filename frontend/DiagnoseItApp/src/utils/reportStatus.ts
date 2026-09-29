export type ReportParseStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export function isReportParsing(status?: string): boolean {
  return status === 'PENDING' || status === 'PROCESSING';
}

export function statusBadgeClass(status?: string, isParsed?: boolean): string {
  switch (status) {
    case 'COMPLETED':
      return 'success';
    case 'FAILED':
      return 'error';
    case 'PROCESSING':
    case 'PENDING':
      return 'warning';
    default:
      return isParsed ? 'success' : 'muted';
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

export function testResultBadgeClass(status: string): string {
  switch (status) {
    case 'NORMAL':
      return 'success';
    case 'HIGH':
      return 'error';
    case 'LOW':
      return 'warning';
    default:
      return 'muted';
  }
}

import { badgeColor } from './colors';

export function testResultColor(status: string): string {
  return badgeColor(testResultBadgeClass(status));
}
