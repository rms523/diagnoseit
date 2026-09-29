import type { ReportBrief, ReportNeighbors } from '../services/api';

const ORDER_KEY = 'diagnoseit.reportListOrder';
const SEARCH_KEY = 'diagnoseit.reportListSearch';
// A sort is a preference, not part of one visit, so it outlives the tab the order and search belong to.
// Each list keeps its own: sorting reports by name says nothing about how prescriptions should be sorted.
const SORT_KEYS = {
  reports: 'diagnoseit.reportListSort',
  prescriptions: 'diagnoseit.prescriptionListSort',
} as const;

export type SortedList = keyof typeof SORT_KEYS;

/** The sort last chosen on a list, for when the address carries none. */
export function savedListSort(list: SortedList): string | null {
  try {
    return localStorage.getItem(SORT_KEYS[list]);
  } catch {
    return null;
  }
}

/** Remember a sort the user chose, so the list opens that way next time. */
export function saveListSort(list: SortedList, value: string): void {
  try {
    localStorage.setItem(SORT_KEYS[list], value);
  } catch {
    /* the list still sorts, it just forgets the choice */
  }
}

/** Remember the report list as last shown (filtered and sorted) and its address, for this browser tab. */
export function saveReportListView(reports: ReportBrief[], search: string): void {
  try {
    sessionStorage.setItem(ORDER_KEY, JSON.stringify(reports.map(({ id, title }) => ({ id, title }))));
    sessionStorage.setItem(SEARCH_KEY, search);
  } catch {
    /* report pages fall back to the default order and an unfiltered list */
  }
}

/** The report list with the search, sort, and filter it was last shown with. */
export function reportListPath(): string {
  try {
    const search = sessionStorage.getItem(SEARCH_KEY) ?? '';
    return `/medical-reports${search.startsWith('?') ? search : ''}`;
  } catch {
    return '/medical-reports';
  }
}

/** The reports before and after this one as the list was last shown, or null when it was not in that list. */
export function listedReportNeighbors(reportId: number): ReportNeighbors | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(ORDER_KEY) ?? 'null');
    if (!Array.isArray(value)) return null;
    const listed = value.filter(
      (item): item is ReportBrief =>
        typeof item === 'object' && item !== null
        && typeof (item as ReportBrief).id === 'number' && typeof (item as ReportBrief).title === 'string'
    );
    const index = listed.findIndex(item => item.id === reportId);
    if (index === -1) return null;
    return {
      previous: listed[index - 1] ?? null,
      next: listed[index + 1] ?? null,
      position: index + 1,
      total: listed.length,
    };
  } catch {
    return null;
  }
}
