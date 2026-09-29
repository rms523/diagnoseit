import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { apiService } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';
import { IconClose, IconReports, IconSearch, IconTrash } from './Icons';
import { saveListSort, saveReportListView, savedListSort } from '../utils/reportList';
import TestResultSearch from './TestResultSearch';
import type { BulkUploadResult, MedicalReport } from '../services/api';
import { parseDateInput, todayIsoDate } from '../utils/dates';
import {
  aiReviewBadge,
  isReportParsing,
  reportMatchesFilter,
  statusBadgeClass,
  statusLabel,
  type ReportStatusFilter,
} from '../utils/reportStatus';

const REPORT_TYPES = [
  { value: 'LAB', label: 'Laboratory Report' },
  { value: 'BLOOD', label: 'Blood Test' },
  { value: 'URINE', label: 'Urine Test' },
  { value: 'XRAY', label: 'X-Ray' },
  { value: 'MRI', label: 'MRI Scan' },
  { value: 'CT', label: 'CT Scan' },
  { value: 'OTHER', label: 'Other' },
];

const STATUS_FILTERS: { key: ReportStatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'parsed', label: 'Parsed' },
  { key: 'processing', label: 'Processing' },
  { key: 'failed', label: 'Failed' },
];

type ReportSort = 'report_date_desc' | 'report_date_asc' | 'added_desc' | 'added_asc' | 'title_asc' | 'title_desc';

const SORT_OPTIONS: { value: ReportSort; label: string }[] = [
  { value: 'report_date_desc', label: 'Report date, newest first' },
  { value: 'report_date_asc', label: 'Report date, oldest first' },
  { value: 'added_desc', label: 'Date added, newest first' },
  { value: 'added_asc', label: 'Date added, oldest first' },
  { value: 'title_asc', label: 'Name, A to Z' },
  { value: 'title_desc', label: 'Name, Z to A' },
];
const DEFAULT_SORT: ReportSort = 'report_date_desc';

const byTitle = (a: MedicalReport, b: MedicalReport) =>
  a.title.localeCompare(b.title, undefined, { numeric: true, sensitivity: 'base' });
const byReportDate = (a: MedicalReport, b: MedicalReport) =>
  a.report_date.localeCompare(b.report_date) || a.created_at.localeCompare(b.created_at);
const byAdded = (a: MedicalReport, b: MedicalReport) => a.created_at.localeCompare(b.created_at);

const SORTERS: Record<ReportSort, (a: MedicalReport, b: MedicalReport) => number> = {
  report_date_desc: (a, b) => byReportDate(b, a),
  report_date_asc: byReportDate,
  added_desc: (a, b) => byAdded(b, a),
  added_asc: byAdded,
  title_asc: byTitle,
  title_desc: (a, b) => byTitle(b, a),
};

/** Every word of the query appears in the report's name or lab name, ignoring case. */
function matchesReportQuery(report: MedicalReport, query: string): boolean {
  const haystack = `${report.title} ${report.lab_name ?? ''}`.toLocaleLowerCase();
  return query.toLocaleLowerCase().split(/\s+/).filter(Boolean).every(word => haystack.includes(word));
}

const SELECTION_KEY = 'diagnoseit.selectedReportIds';

/** Reports selected for AI review in this tab, so the selection survives opening a report. */
function storedSelection(): number[] {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(SELECTION_KEY) ?? '[]');
    return Array.isArray(value) ? value.filter((id): id is number => typeof id === 'number') : [];
  } catch {
    return [];
  }
}

/** Parsed reports can be sent for AI review unless one is already queued or running. */
function canSelectForReview(report: MedicalReport): boolean {
  return report.status === 'COMPLETED' && report.ai_review_summary?.status !== 'pending';
}

const AIReviewBadge: React.FC<{ summary: MedicalReport['ai_review_summary'] }> = ({ summary }) => {
  const badge = aiReviewBadge(summary);
  if (!badge) return null;
  return (
    <span className={`badge ${badge.className}`}>
      {badge.busy && <span className="spinner" style={{ width: 12, height: 12, marginRight: 4 }} />}
      {badge.label}
    </span>
  );
};

const MedicalReports: React.FC = () => {
  const navigate = useNavigate();
  const { toast, confirm } = useToast();
  const [reports, setReports] = useState<MedicalReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const location = useLocation();
  // Search, sort, and status filter live in the address, so they survive opening a report and coming back.
  const [searchParams, setSearchParams] = useSearchParams();
  const nameQuery = searchParams.get('q') ?? '';
  // Without a sort in the address (arriving from the menu, or a new session), the last one chosen is used.
  const sort =
    SORT_OPTIONS.find(option => option.value === (searchParams.get('sort') ?? savedListSort('reports')))?.value
    ?? DEFAULT_SORT;
  const statusFilter = STATUS_FILTERS.find(filter => filter.key === searchParams.get('status'))?.key ?? 'all';
  const updateParam = useCallback(
    (key: string, value: string) =>
      setSearchParams(previous => {
        const next = new URLSearchParams(previous);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      }, { replace: true }),
    [setSearchParams]
  );
  const setStatusFilter = (filter: ReportStatusFilter) => updateParam('status', filter === 'all' ? '' : filter);
  const [error, setError] = useState('');
  const [reviewAvailable, setReviewAvailable] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>(storedSelection);
  const [queueingReviews, setQueueingReviews] = useState(false);

  const fetchReports = useCallback(async (silent = false) => {
    try {
      const data = await apiService.getMedicalReports();
      setReports(data);
      setError('');
    } catch {
      if (!silent) setError('Failed to load reports');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  useEffect(() => {
    // Keep refreshing while any report is parsing or has an AI review queued or running.
    if (!reports.some(r => isReportParsing(r.status) || r.ai_review_summary?.status === 'pending')) return;
    const id = window.setInterval(() => fetchReports(true), 5000);
    return () => clearInterval(id);
  }, [reports, fetchReports]);

  const filteredReports = useMemo(
    () =>
      reports
        .filter(r => reportMatchesFilter(r, statusFilter) && matchesReportQuery(r, nameQuery))
        .sort(SORTERS[sort]),
    [reports, statusFilter, nameQuery, sort]
  );

  // Report pages move to the previous or next report in this list, as filtered and sorted here.
  useEffect(() => {
    if (!loading) saveReportListView(filteredReports, location.search);
  }, [filteredReports, loading, location.search]);

  useEffect(() => {
    apiService
      .getAIStatus()
      .then(status => setReviewAvailable(status.report_review.available))
      .catch(() => setReviewAvailable(false));
  }, []);

  const selectableReports = useMemo(() => filteredReports.filter(canSelectForReview), [filteredReports]);
  const allSelected = selectableReports.length > 0 && selectableReports.every(r => selectedIds.includes(r.id));

  useEffect(() => {
    try {
      sessionStorage.setItem(SELECTION_KEY, JSON.stringify(selectedIds));
    } catch {
      /* the selection just does not survive leaving the page */
    }
  }, [selectedIds]);

  // Drop reports from the selection once they start parsing or reviewing, or disappear.
  useEffect(() => {
    if (loading) return;
    setSelectedIds(prev => {
      const next = prev.filter(id => reports.some(r => r.id === id && canSelectForReview(r)));
      return next.length === prev.length ? prev : next;
    });
  }, [reports, loading]);

  const toggleSelected = (id: number) =>
    setSelectedIds(prev => (prev.includes(id) ? prev.filter(selected => selected !== id) : [...prev, id]));

  const toggleAllSelected = () => {
    const visibleIds = selectableReports.map(r => r.id);
    setSelectedIds(prev =>
      allSelected ? prev.filter(id => !visibleIds.includes(id)) : [...new Set([...prev, ...visibleIds])]
    );
  };

  const statusCounts = useMemo(() => ({
    all: reports.length,
    parsed: reports.filter(r => reportMatchesFilter(r, 'parsed')).length,
    processing: reports.filter(r => reportMatchesFilter(r, 'processing')).length,
    failed: reports.filter(r => reportMatchesFilter(r, 'failed')).length,
  }), [reports]);

  const handleDelete = async (id: number) => {
    const ok = await confirm('Delete this report and all its test results?');
    if (!ok) return;
    try {
      await apiService.deleteMedicalReport(id);
      setReports(prev => prev.filter(r => r.id !== id));
      toast('Report deleted', 'success');
    } catch {
      toast('Failed to delete report', 'error');
    }
  };

  const reviewSelected = async () => {
    // Reports are reviewed one at a time, in list order.
    const chosen = reports.filter(r => selectedIds.includes(r.id));
    const replacing = chosen.filter(r => r.ai_review_summary?.status === 'completed').length;
    if (replacing > 0) {
      const ok = await confirm(
        `${replacing} of these report${replacing === 1 ? ' already has' : 's already have'} an AI review. ` +
          'Reviewing again replaces its suggestions and undo history. Continue?'
      );
      if (!ok) return;
    }
    setQueueingReviews(true);
    try {
      const result = await apiService.reviewReportsWithAI(chosen.map(r => r.id));
      setSelectedIds([]);
      const queued = result.queued.length;
      if (queued > 0) {
        toast(`${queued} report${queued === 1 ? '' : 's'} queued for AI review, reviewed one at a time`, 'success');
      }
      if (result.skipped.length > 0) {
        toast(`${result.skipped.length} skipped: ${result.skipped[0].reason}`, 'info');
      }
      await fetchReports(true);
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not queue the AI reviews'), 'error');
    } finally {
      setQueueingReviews(false);
    }
  };

  const stopReview = async (report: MedicalReport, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await apiService.stopReportReview(report.id);
      toast('AI review stopped', 'info');
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not stop the AI review'), 'error');
    }
    fetchReports(true);
  };

  const exportCSV = (report: MedicalReport, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!report.test_results?.length) {
      toast('No test results to export', 'info');
      return;
    }
    const headers = 'Test Name,Value,Unit,Reference Range,Status';
    const rows = report.test_results.map(tr =>
      `"${tr.test_name}",${tr.value},"${tr.unit}","${tr.reference_range}",${tr.status}`
    );
    const blob = new Blob([[headers, ...rows].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${report.title.replace(/[^a-zA-Z0-9]/g, '_')}_results.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast('CSV exported', 'success');
  };

  if (loading) {
    return (
      <div className="stack">
        <div className="skeleton" style={{ height: 48, width: 280 }} />
        {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 120 }} />)}
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Medical Reports</h1>
          <p className="page-subtitle">Upload and manage your lab reports</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowUpload(true)}>
          Upload report
        </button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 'var(--space-4)' }}>{error}</div>}

      {reports.length > 0 && <TestResultSearch onResultDeleted={() => fetchReports(true)} />}

      {reports.length > 0 && (
        <div className="row-between" style={{ marginBottom: 'var(--space-6)', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <div className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            {STATUS_FILTERS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                className={`btn btn-sm ${statusFilter === key ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setStatusFilter(key)}
              >
                {label} ({statusCounts[key]})
              </button>
            ))}
          </div>
          <div className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap', flex: '1 1 360px', justifyContent: 'flex-end' }}>
            <div className="search-bar" style={{ flex: '1 1 220px', maxWidth: 320 }}>
              <span className="search-bar-icon" aria-hidden><IconSearch size={16} /></span>
              <input
                className="form-input"
                type="search"
                value={nameQuery}
                onChange={e => updateParam('q', e.target.value)}
                placeholder="Search reports by name or lab"
                aria-label="Search reports by name or lab"
              />
            </div>
            <select
              className="form-select"
              style={{ width: 'auto' }}
              value={sort}
              onChange={e => {
                saveListSort('reports', e.target.value);
                updateParam('sort', e.target.value === DEFAULT_SORT ? '' : e.target.value);
              }}
              aria-label="Sort reports"
            >
              {SORT_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {nameQuery.trim() && filteredReports.length > 0 && (
        <p className="form-hint" style={{ marginTop: 'calc(-1 * var(--space-4))', marginBottom: 'var(--space-4)' }}>
          {filteredReports.length} of {statusCounts[statusFilter]} report{statusCounts[statusFilter] === 1 ? '' : 's'} match “{nameQuery.trim()}”
        </p>
      )}

      {reviewAvailable && selectableReports.length > 0 && (
        <div className="row" style={{ marginBottom: 'var(--space-4)', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <label className="row form-hint" style={{ gap: 'var(--space-2)' }}>
            <input type="checkbox" className="report-select-checkbox" checked={allSelected} onChange={toggleAllSelected} />
            Select all parsed ({selectableReports.length})
          </label>
          {selectedIds.length > 0 && (
            <>
              <button type="button" className="btn btn-primary btn-sm" onClick={reviewSelected} disabled={queueingReviews}>
                {queueingReviews
                  ? 'Queueing…'
                  : `AI review ${selectedIds.length} report${selectedIds.length === 1 ? '' : 's'}`}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelectedIds([])}>
                Clear selection
              </button>
            </>
          )}
        </div>
      )}

      {reports.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-state-icon"><IconReports size={32} /></div>
          <div className="empty-state-title">No medical reports</div>
          <div className="empty-state-text">Upload your first lab report to get started with health tracking</div>
          <button className="btn btn-primary" onClick={() => setShowUpload(true)}>Upload report</button>
        </div>
      ) : filteredReports.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-state-title">
            {nameQuery.trim() ? `No ${statusFilter === 'all' ? '' : `${statusFilter} `}reports match “${nameQuery.trim()}”` : `No ${statusFilter} reports`}
          </div>
          <div className="empty-state-text">Try another search or filter, or upload a new report</div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() =>
              setSearchParams(previous => {
                const next = new URLSearchParams(previous);
                next.delete('q');
                next.delete('status');
                return next;
              }, { replace: true })
            }
          >
            Show all reports
          </button>
        </div>
      ) : (
        <div className="stack stagger-children">
          {filteredReports.map(report => (
            <Link
              key={report.id}
              to={`/medical-reports/${report.id}`}
              className="card report-list-link"
              style={{ textDecoration: 'none', display: 'block' }}
            >
              <div className="row-between">
                <div className="row" style={{ gap: 'var(--space-3)', minWidth: 0 }}>
                  {reviewAvailable && (
                    <input
                      type="checkbox"
                      className="report-select-checkbox"
                      aria-label={`Select ${report.title} for AI review`}
                      title={canSelectForReview(report) ? 'Select for AI review' : 'Only parsed reports without a running AI review can be selected'}
                      checked={selectedIds.includes(report.id)}
                      disabled={!canSelectForReview(report)}
                      onClick={e => e.stopPropagation()}
                      onChange={() => toggleSelected(report.id)}
                    />
                  )}
                  <div>
                    <div style={{ fontSize: 'var(--font-base)', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {report.title}
                    </div>
                    <div className="font-mono" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                      {report.lab_name && `${report.lab_name} · `}
                      {REPORT_TYPES.find(t => t.value === report.report_type)?.label || report.report_type} ·{' '}
                      {new Date(`${report.report_date}T00:00:00`).toLocaleDateString()}
                      {report.test_results?.length ? ` · ${report.test_results.length} results` : ''}
                    </div>
                  </div>
                </div>
                <div className="row" style={{ gap: 'var(--space-2)' }} onClick={e => e.preventDefault()}>
                  <span className={`badge ${statusBadgeClass(report.status, report.is_parsed)}`}>
                    {isReportParsing(report.status) && <span className="spinner" style={{ width: 12, height: 12, marginRight: 4 }} />}
                    {statusLabel(report.status, report.is_parsed)}
                  </span>
                  <AIReviewBadge summary={report.ai_review_summary} />
                  {report.ai_review_summary?.status === 'pending' && (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={e => stopReview(report, e)}>
                      Stop AI review
                    </button>
                  )}
                  {report.test_results && report.test_results.length > 0 && (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={e => exportCSV(report, e)}>
                      CSV
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    aria-label="Delete report"
                    onClick={e => { e.preventDefault(); e.stopPropagation(); handleDelete(report.id); }}
                  >
                    <IconTrash size={14} />
                  </button>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onSuccess={(report) => {
            setShowUpload(false);
            toast('Report uploaded — parsing started', 'success');
            navigate(`/medical-reports/${report.id}`);
          }}
          onBulkSuccess={() => {
            fetchReports(true);
          }}
        />
      )}

      <style>{`
        .report-list-link:hover { border-color: var(--border-color-hover); }
        .report-list-link .badge .spinner { display: inline-block; vertical-align: middle; }
        .report-select-checkbox { width: 20px; height: 20px; flex-shrink: 0; margin: 0; accent-color: var(--teal); cursor: pointer; }
        .report-select-checkbox:disabled { cursor: not-allowed; }
      `}</style>
    </div>
  );
};

interface UploadModalProps {
  onClose: () => void;
  onSuccess: (report: MedicalReport) => void;
  onBulkSuccess: () => void;
}

const UploadModal: React.FC<UploadModalProps> = ({ onClose, onSuccess, onBulkSuccess }) => {
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<'single' | 'bulk'>('single');
  const [file, setFile] = useState<File | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [form, setForm] = useState({
    title: '',
    lab_name: '',
    report_type: 'LAB',
  });
  // Free text so dates can be typed or pasted; parsed to YYYY-MM-DD on blur, paste, and submit.
  const [dateText, setDateText] = useState(todayIsoDate);
  const [dateError, setDateError] = useState('');
  const datePickerRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [bulkResults, setBulkResults] = useState<BulkUploadResult | null>(null);
  const [reviewAvailable, setReviewAvailable] = useState(false);
  const [aiReview, setAiReview] = useState(false);

  // The "review with AI" checkbox starts from the shared automatic review setting.
  useEffect(() => {
    let cancelled = false;
    apiService
      .getAIStatus()
      .then(status => {
        if (cancelled) return;
        setReviewAvailable(status.report_review.available);
        setAiReview(status.report_review.available && status.report_review.auto_review);
      })
      .catch(() => {
        if (!cancelled) setReviewAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Without a configured review model there is nothing to choose, so AI settings decide.
  const reviewChoice = reviewAvailable ? aiReview : undefined;

  const switchMode = (next: 'single' | 'bulk') => {
    setMode(next);
    setFile(null);
    setFiles([]);
    setBulkResults(null);
    setError('');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files ?? []);
    if (mode === 'single' && dropped[0]) {
      setFile(dropped[0]);
      if (!form.title) {
        setForm(prev => ({ ...prev, title: dropped[0].name.replace(/\.[^/.]+$/, '') }));
      }
    } else if (mode === 'bulk') {
      setFiles(prev => [...prev, ...dropped]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    if (mode === 'single' && selected[0]) {
      setFile(selected[0]);
      if (!form.title) {
        setForm(prev => ({ ...prev, title: selected[0].name.replace(/\.[^/.]+$/, '') }));
      }
    } else if (mode === 'bulk') {
      setFiles(prev => [...prev, ...selected]);
    }
    e.target.value = '';
  };

  const removeFile = (index?: number) => {
    if (mode === 'single') {
      setFile(null);
    } else if (index !== undefined) {
      setFiles(prev => prev.filter((_, i) => i !== index));
    }
  };

  const updateDateText = (value: string) => {
    setDateText(value);
    setDateError('');
  };

  const normalizeDateText = () => {
    const parsed = parseDateInput(dateText);
    if (parsed) {
      setDateText(parsed);
    } else {
      setDateError('Use a date like 2026-05-14, 14/05/2026, or 14 May 2026');
    }
  };

  const handleDatePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const parsed = parseDateInput(e.clipboardData.getData('text'));
    if (parsed) {
      e.preventDefault();
      updateDateText(parsed);
    }
  };

  const openDatePicker = () => {
    const picker = datePickerRef.current;
    if (!picker) return;
    picker.value = parseDateInput(dateText) ?? '';
    try {
      picker.showPicker();
    } catch {
      // Browsers without showPicker still open the picker from focus/click on the input.
      picker.focus();
      picker.click();
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setBulkResults(null);

    if (mode === 'single') {
      if (!file || !form.title) {
        setError('Title and file are required');
        return;
      }
      const reportDate = parseDateInput(dateText);
      if (!reportDate) {
        setDateError('Use a date like 2026-05-14, 14/05/2026, or 14 May 2026');
        setError('Enter a valid report date');
        return;
      }
      setUploading(true);
      try {
        const report = await apiService.uploadMedicalReport(
          file,
          form.title,
          form.report_type,
          form.lab_name,
          reportDate,
          undefined,
          reviewChoice
        );
        onSuccess(report);
      } catch {
        setError('Upload failed. Please try again.');
      } finally {
        setUploading(false);
      }
      return;
    }

    if (files.length === 0) {
      setError('Select at least one file');
      return;
    }

    setUploading(true);
    try {
      const result = await apiService.bulkUploadMedicalReports(files, reviewChoice);
      setBulkResults(result);
      setFiles([]);
      onBulkSuccess();
      if (result.errors === 0) {
        toast(`All ${result.created} reports uploaded`, 'success');
      } else {
        toast(`${result.created} uploaded, ${result.errors} failed`, result.created > 0 ? 'info' : 'error');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message.replace(/^API Error: \d+ \w+ - /, '') : 'Bulk upload failed';
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="modal-header">
          <h2 className="modal-title">Upload medical report</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <IconClose size={18} />
          </button>
        </div>

        <div className="row" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-4)', padding: '0 var(--space-6)' }}>
          <button
            type="button"
            className={`btn btn-sm ${mode === 'single' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ flex: 1 }}
            onClick={() => switchMode('single')}
          >
            Single
          </button>
          <button
            type="button"
            className={`btn btn-sm ${mode === 'bulk' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ flex: 1 }}
            onClick={() => switchMode('bulk')}
          >
            Bulk
          </button>
        </div>

        {error && <div className="alert alert-error" style={{ margin: '0 var(--space-6) var(--space-4)' }}>{error}</div>}

        <form onSubmit={handleSubmit} className="modal-body">
          <div
            className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,application/pdf"
              multiple={mode === 'bulk'}
              hidden
              onChange={handleFileChange}
            />
            {mode === 'single' ? (
              file ? (
                <>
                  <div className="upload-zone-text">{file.name}</div>
                  <div className="upload-zone-hint">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
                </>
              ) : (
                <>
                  <div className="upload-zone-text">Drag and drop or click to select</div>
                  <div className="upload-zone-hint">PDF up to 10MB</div>
                </>
              )
            ) : files.length > 0 ? (
              <>
                <div className="upload-zone-text">{files.length} file{files.length !== 1 ? 's' : ''} selected</div>
                <div className="upload-zone-hint">Click to add more</div>
              </>
            ) : (
              <>
                <div className="upload-zone-text">Drag and drop or click to select files</div>
                <div className="upload-zone-hint">Name files YYYY-MM-DD_lab.pdf (e.g. 2026-05-14_lalpath.pdf) to set date and lab</div>
              </>
            )}
          </div>

          {mode === 'bulk' && files.length > 0 && (
            <ul className="stack" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-4)', listStyle: 'none', padding: 0 }}>
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`} className="row-between" style={{ fontSize: 'var(--font-sm)' }}>
                  <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{f.name}</span>
                  <button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove ${f.name}`} onClick={() => removeFile(i)}>
                    <IconClose size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {mode === 'single' && (
            <>
              <div className="form-group">
                <label className="form-label" htmlFor="upload-title">Report title *</label>
                <input
                  id="upload-title"
                  className="form-input"
                  placeholder="e.g. Annual blood work 2024"
                  value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="upload-type">Report type</label>
                  <select
                    id="upload-type"
                    className="form-select"
                    value={form.report_type}
                    onChange={e => setForm({ ...form, report_type: e.target.value })}
                  >
                    {REPORT_TYPES.map(t => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="upload-date">Report date</label>
                  <div className="row" style={{ gap: 'var(--space-2)', position: 'relative' }}>
                    <input
                      id="upload-date"
                      className="form-input"
                      style={{ flex: 1, minWidth: 0 }}
                      placeholder="e.g. 14/05/2026"
                      autoComplete="off"
                      value={dateText}
                      onChange={e => updateDateText(e.target.value)}
                      onPaste={handleDatePaste}
                      onBlur={normalizeDateText}
                      aria-invalid={dateError ? true : undefined}
                      aria-describedby={dateError ? 'upload-date-error' : undefined}
                      required
                    />
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={openDatePicker}
                      aria-label="Pick report date from calendar"
                    >
                      Calendar
                    </button>
                    {/* Native picker kept rendered (not display:none) so showPicker() can open it. */}
                    <input
                      ref={datePickerRef}
                      type="date"
                      tabIndex={-1}
                      aria-hidden="true"
                      style={{ position: 'absolute', right: 0, bottom: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
                      onChange={e => {
                        if (e.target.value) updateDateText(e.target.value);
                      }}
                    />
                  </div>
                  {dateError && <div id="upload-date-error" className="form-error">{dateError}</div>}
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="upload-lab">Lab name</label>
                <input
                  id="upload-lab"
                  className="form-input"
                  placeholder="e.g. LabCorp, Quest Diagnostics"
                  value={form.lab_name}
                  onChange={e => setForm({ ...form, lab_name: e.target.value })}
                />
              </div>
            </>
          )}

          <label className="row" style={{ gap: 'var(--space-2)', alignItems: 'flex-start', marginBottom: 'var(--space-4)' }}>
            <input
              type="checkbox"
              checked={aiReview}
              disabled={!reviewAvailable || uploading}
              onChange={e => setAiReview(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Review with AI after parsing
              <span className="form-hint" style={{ display: 'block' }}>
                {reviewAvailable ? (
                  mode === 'bulk'
                    ? 'Each file is reviewed once it is parsed, with suggestions on its report page. Every file costs one or more model calls.'
                    : 'Suggestions appear on the report page. This costs one or more model calls.'
                ) : (
                  <>
                    Set up a report review model in{' '}
                    <Link to="/settings/ai" onClick={onClose}>AI settings</Link> to use this.
                  </>
                )}
              </span>
            </span>
          </label>

          {bulkResults && (
            <div className="card report-section" style={{ marginBottom: 'var(--space-4)' }}>
              <p className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>Bulk upload summary</p>
              <div className="row" style={{ gap: 'var(--space-4)', flexWrap: 'wrap', marginBottom: 'var(--space-3)' }}>
                <span className="badge badge-success">{bulkResults.created} created</span>
                {bulkResults.errors > 0 && <span className="badge badge-danger">{bulkResults.errors} failed</span>}
                <span className="badge badge-muted">{bulkResults.total} total</span>
              </div>
              {bulkResults.error_details.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: 'var(--space-4)', fontSize: 'var(--font-sm)', color: 'var(--text-secondary)' }}>
                  {bulkResults.error_details.map((err, i) => (
                    <li key={i}>{err.file}: {err.error}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={uploading || (mode === 'single' ? !file : files.length === 0)}>
              {uploading ? (
                <><span className="spinner" /> Uploading…</>
              ) : mode === 'bulk' ? (
                `Upload ${files.length || ''} file${files.length !== 1 ? 's' : ''}`.trim()
              ) : (
                'Upload'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default MedicalReports;
