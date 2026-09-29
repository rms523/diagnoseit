import { theme } from '../theme/theme';
import { tokens } from '../theme/tokens';

/** Status badge colors aligned with Specimen Ledger tokens */
export function badgeColor(key: string): string {
  switch (key) {
    case 'success':
      return theme.colors.primary;
    case 'error':
      return theme.colors.error;
    case 'warning':
      return tokens.amber;
    default:
      return theme.colors.onSurfaceVariant;
  }
}

export function getSeverityColor(severity: number): string {
  switch (severity) {
    case 1:
      return tokens.sage;
    case 2:
      return tokens.amber;
    case 3:
      return tokens.coral;
    case 4:
      return theme.colors.error;
    default:
      return theme.colors.primary;
  }
}

export function getReportTypeColor(type: string): string {
  switch (type) {
    case 'BLOOD':
      return tokens.coral;
    case 'LAB':
      return theme.colors.primary;
    case 'XRAY':
      return tokens.slate;
    case 'MRI':
      return tokens.amber;
    case 'CT':
      return tokens.sage;
    default:
      return theme.colors.onSurfaceVariant;
  }
}

export function getLabStatusColor(status: string): string {
  const s = status.toUpperCase();
  if (s === 'NORMAL') return theme.colors.primary;
  if (s.includes('HIGH') || s === 'CRITICAL_HIGH') return theme.colors.error;
  if (s.includes('LOW') || s === 'CRITICAL_LOW') return tokens.amber;
  return theme.colors.onSurfaceVariant;
}

export function getConfidenceColor(score: number): string {
  if (score >= 4) return theme.colors.primary;
  if (score >= 3) return tokens.amber;
  return theme.colors.error;
}
