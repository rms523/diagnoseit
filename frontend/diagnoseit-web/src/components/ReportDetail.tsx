import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { listedReportNeighbors, reportListPath } from '../utils/reportList';
import { apiService } from '../services/api';
import type {
  AppliedReviewChange,
  LabTestType,
  LabTestTypeUnit,
  MedicalReport,
  NewTestResult,
  ReportReview,
  ReviewActionResponse,
  ReviewSuggestion,
  StoredReportReview,
  TestResult,
} from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';
import { copyText, downloadText } from '../utils/clipboard';
import AIChatPanel from './AIChatPanel';
import {
  isReportParsing,
  statusBadgeClass,
  statusLabel,
  testResultBadgeClass,
} from '../utils/reportStatus';

const REPORT_TYPES: Record<string, string> = {
  LAB: 'Laboratory Report',
  BLOOD: 'Blood Test',
  URINE: 'Urine Test',
  XRAY: 'X-Ray',
  MRI: 'MRI Scan',
  CT: 'CT Scan',
  OTHER: 'Other',
};

const RESULT_STATUSES = ['NORMAL', 'HIGH', 'LOW', 'ABNORMAL'];

const EMPTY_NEW_RESULT: NewTestResult = { test_name: '', value: '', unit: '', reference_range: '' };

const FIELD_LABELS: Record<string, string> = {
  test_name: 'Name',
  value: 'Value',
  unit: 'Unit',
  reference_range: 'Reference',
  status: 'Status',
};

type PendingSuggestion = ReviewSuggestion & { uid: number };

const normalizeName = (value: string) => value.trim().replace(/\s+/g, ' ').toLowerCase();

/** Match a typed test name to the catalog the way the API does: by name, display name, or alias. */
function findCatalogType(types: LabTestType[], name: string): LabTestType | undefined {
  const key = normalizeName(name);
  if (!key) return undefined;
  return types.find(type =>
    [type.name, type.display_name, ...(type.aliases ?? [])].some(value => normalizeName(value) === key)
  );
}

const REVIEW_INPUT_LABELS: Record<ReportReview['input_mode'], string> = {
  text: 'PDF text',
  images: 'page images',
  ocr: 'OCR text',
  images_ocr: 'page images + OCR text',
};

const reviewOptionCheckbox: React.CSSProperties = { width: 18, height: 18, margin: 0, accentColor: 'var(--teal)' };

const ReportDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const reportId = Number(id);
  const resultId = Number(searchParams.get('result'));
  const navigate = useNavigate();
  const { toast, confirm } = useToast();

  const [report, setReport] = useState<MedicalReport | null>(null);
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ value: '', unit: '', reference_range: '' });
  const [editUnits, setEditUnits] = useState<LabTestTypeUnit[]>([]);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const notifiedRef = useRef(false);

  const [catalog, setCatalog] = useState<LabTestType[]>([]);
  const [unitsByType, setUnitsByType] = useState<Record<string, LabTestTypeUnit[]>>({});
  const [adding, setAdding] = useState(false);
  const [newResult, setNewResult] = useState<NewTestResult>(EMPTY_NEW_RESULT);
  const [savingNew, setSavingNew] = useState(false);

  const [showPdf, setShowPdf] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState('');
  const openedTrendResultRef = useRef('');

  const [reviewAvailable, setReviewAvailable] = useState(false);
  const [ocrAvailable, setOcrAvailable] = useState(false);
  // Per-review choices for PDFs whose text layer parses badly: read the pages with OCR, and send page images.
  const [reviewWithOcr, setReviewWithOcr] = useState(false);
  const [reviewWithImages, setReviewWithImages] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [review, setReview] = useState<ReportReview | null>(null);
  const [pending, setPending] = useState<PendingSuggestion[]>([]);
  const [applying, setApplying] = useState<'all' | number | null>(null);
  const [undoingId, setUndoingId] = useState<number | null>(null);

  const showStoredReview = useCallback((stored: StoredReportReview | null | undefined) => {
    if (stored?.status === 'completed') {
      setReview(stored);
      setPending(stored.suggestions.map(suggestion => ({ ...suggestion, uid: suggestion.id })));
    } else {
      setReview(null);
      setPending([]);
    }
  }, []);

  const loadReport = useCallback(async (): Promise<MedicalReport | null> => {
    if (!reportId || Number.isNaN(reportId)) return null;
    try {
      const data = await apiService.getMedicalReport(reportId);
      setReport(data);
      setTestResults(data.test_results ?? []);
      showStoredReview(data.ai_review);
      return data;
    } catch {
      setReport(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [reportId, showStoredReview]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  useEffect(() => {
    notifiedRef.current = false;
  }, [reportId]);

  useEffect(() => {
    apiService
      .getAIStatus()
      .then(status => {
        setReviewAvailable(status.report_review.available);
        setOcrAvailable(Boolean(status.ocr?.available));
      })
      .catch(() => setReviewAvailable(false));
  }, []);

  // Release the in-memory PDF when it is replaced or the page closes.
  useEffect(() => () => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  }, [pdfUrl]);

  const reportStatus = report?.status;
  const reviewRunning = report?.ai_review?.status === 'pending';

  const showFinishedReview = useCallback(async () => {
    const stored = (await loadReport())?.ai_review;
    if (stored?.status === 'completed') {
      const count = stored.suggestions.length;
      const autoApplied = (stored.applied ?? []).filter(change => change.automatic).length;
      const outcomes = [
        autoApplied ? `${autoApplied} safe fix${autoApplied === 1 ? '' : 'es'} applied` : '',
        count ? `${count} suggestion${count === 1 ? '' : 's'} to review` : '',
      ].filter(Boolean);
      toast(
        outcomes.length ? `AI review: ${outcomes.join(', ')}` : 'AI review found nothing to change',
        outcomes.length ? 'success' : 'info'
      );
    } else if (stored?.status === 'failed') {
      toast('AI review failed', 'error');
    }
  }, [loadReport, toast]);

  // Poll while the report is parsing, then while its automatic AI review runs.
  useEffect(() => {
    if (!isReportParsing(reportStatus) && !reviewRunning) return;

    const interval = window.setInterval(async () => {
      try {
        const status = await apiService.getReportStatus(reportId);
        if (!isReportParsing(reportStatus)) {
          if (status.ai_review_status !== 'pending') await showFinishedReview();
        } else if (status.status === 'COMPLETED' || status.status === 'FAILED') {
          await loadReport();
          if (!notifiedRef.current) {
            notifiedRef.current = true;
            if (status.status === 'COMPLETED') {
              toast('Report parsing completed', 'success');
            } else {
              toast(status.parse_error || 'Report parsing failed', 'error');
            }
          }
        } else {
          setReport(prev => prev ? { ...prev, status: status.status } : prev);
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [reportStatus, reviewRunning, reportId, loadReport, showFinishedReview, toast]);

  const matchedType = useMemo(() => findCatalogType(catalog, newResult.test_name), [catalog, newResult.test_name]);
  const newResultUnits = matchedType ? unitsByType[matchedType.name] ?? [] : [];

  useEffect(() => {
    if (!matchedType || unitsByType[matchedType.name]) return;
    let cancelled = false;
    apiService
      .getLabTestUnits(matchedType.name)
      .then(units => {
        if (!cancelled) setUnitsByType(prev => ({ ...prev, [matchedType.name]: units }));
      })
      .catch(() => {
        if (!cancelled) setUnitsByType(prev => ({ ...prev, [matchedType.name]: [] }));
      });
    return () => {
      cancelled = true;
    };
  }, [matchedType, unitsByType]);

  const loadUnitsForTest = async (testName: string) => {
    try {
      const units = await apiService.getLabTestUnits(testName);
      setEditUnits(units);
    } catch {
      setEditUnits([]);
    }
  };

  const startEdit = (result: TestResult) => {
    setEditingId(result.id);
    setEditForm({
      value: result.value,
      unit: result.unit,
      reference_range: result.reference_range,
    });
    loadUnitsForTest(result.test_type_name || result.test_name);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({ value: '', unit: '', reference_range: '' });
    setEditUnits([]);
  };

  const saveEdit = async (resultId: number) => {
    try {
      const updated = await apiService.updateTestResult(resultId, editForm);
      setTestResults(prev => prev.map(r => (r.id === resultId ? { ...r, ...updated } : r)));
      cancelEdit();
      toast('Test result updated', 'success');
    } catch {
      toast('Failed to update test result', 'error');
    }
  };

  const convertUnit = async (resultId: number, targetUnit: string) => {
    setConvertingId(resultId);
    try {
      const converted = await apiService.convertTestResultUnit(resultId, targetUnit);
      setTestResults(prev =>
        prev.map(r =>
          r.id === resultId ? { ...r, value: converted.value, unit: converted.unit } : r
        )
      );
      toast(`Converted to ${targetUnit}`, 'success');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to convert unit';
      toast(msg.replace(/^API Error: \d+ \w+ - /, ''), 'error');
    } finally {
      setConvertingId(null);
    }
  };

  const validateResult = async (resultId: number) => {
    try {
      const result = await apiService.validateTestResult(resultId);
      setTestResults(prev =>
        prev.map(r => (r.id === resultId ? { ...r, status: result.status as TestResult['status'] } : r))
      );
      toast(`Status: ${result.status}`, 'info');
    } catch {
      toast('Failed to validate result', 'error');
    }
  };

  const deleteResult = async (result: TestResult) => {
    const ok = await confirm(`Delete the ${result.test_name} result?`);
    if (!ok) return;
    try {
      await apiService.deleteTestResult(reportId, result.id);
      setTestResults(prev => prev.filter(r => r.id !== result.id));
      if (editingId === result.id) cancelEdit();
      toast('Test result deleted', 'success');
    } catch (err) {
      toast(apiErrorMessage(err, 'Failed to delete test result'), 'error');
    }
  };

  const openAddForm = async () => {
    setAdding(true);
    if (catalog.length === 0) {
      try {
        setCatalog(await apiService.getAllLabTestTypes());
      } catch {
        /* custom entries still work without the catalog */
      }
    }
  };

  const closeAddForm = () => {
    setAdding(false);
    setNewResult(EMPTY_NEW_RESULT);
  };

  const saveNewResult = async (e: React.FormEvent) => {
    e.preventDefault();
    const testName = newResult.test_name.trim();
    const value = newResult.value.trim();
    if (!testName || !value) {
      toast('Test and value are required', 'error');
      return;
    }
    setSavingNew(true);
    try {
      let created = await apiService.createTestResult(reportId, {
        test_name: matchedType ? matchedType.display_name : testName,
        value,
        unit: newResult.unit.trim(),
        reference_range: newResult.reference_range.trim(),
      });
      if (created.test_type_name && created.unit) {
        try {
          const validation = await apiService.validateTestResult(created.id);
          if (RESULT_STATUSES.includes(validation.status)) {
            created = { ...created, status: validation.status as TestResult['status'] };
          }
        } catch {
          /* no reference range for this unit; status stays blank */
        }
      }
      setTestResults(prev => [...prev, created]);
      closeAddForm();
      toast(`Added ${created.test_name}`, 'success');
    } catch (err) {
      toast(apiErrorMessage(err, 'Failed to add test result'), 'error');
    } finally {
      setSavingNew(false);
    }
  };

  const toggleChat = () => {
    setShowChat(open => !open);
    // Both panes live in the same column beside the results, so only one can be open at a time.
    setShowPdf(false);
  };

  const togglePdf = useCallback(async () => {
    if (showPdf) {
      setShowPdf(false);
      return;
    }
    setShowPdf(true);
    setShowChat(false);
    if (pdfUrl || !report) return;
    setPdfError('');
    try {
      const blob = await apiService.getMedicalReportFile(report.id);
      setPdfUrl(URL.createObjectURL(new Blob([blob], { type: 'application/pdf' })));
    } catch {
      setPdfError('Could not load the original PDF.');
    }
  }, [showPdf, pdfUrl, report]);

  useEffect(() => {
    if (!report || !Number.isInteger(resultId) || resultId <= 0 || !testResults.some(result => result.id === resultId)) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(`report-result-${resultId}`)?.scrollIntoView({ block: 'center' });
    });
    return () => cancelAnimationFrame(frame);
  }, [report, resultId, testResults, showPdf]);

  useEffect(() => {
    if (!report?.file || !Number.isInteger(resultId) || resultId <= 0 ||
      !testResults.some(result => result.id === resultId)) return;
    const key = `${report.id}:${resultId}`;
    if (openedTrendResultRef.current === key) return;
    openedTrendResultRef.current = key;
    if (!showPdf) void togglePdf();
  }, [report, resultId, testResults, showPdf, togglePdf]);

  const runReview = async () => {
    setReviewing(true);
    try {
      const stored = await apiService.reviewReportWithAI(reportId, {
        ocr: reviewWithOcr && ocrAvailable,
        images: reviewWithImages,
      });
      setReport(prev => (prev ? { ...prev, ai_review: stored } : prev));
      showStoredReview(stored);
    } catch (err) {
      toast(apiErrorMessage(err, 'AI review failed'), 'error');
    } finally {
      setReviewing(false);
    }
  };

  const dismissSuggestion = async (uid: number) => {
    setPending(prev => prev.filter(item => item.uid !== uid));
    try {
      await apiService.dismissReviewSuggestion(reportId, uid);
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not dismiss this suggestion'), 'error');
    }
  };

  const stopReview = async () => {
    setStopping(true);
    try {
      await apiService.stopReportReview(reportId);
      setReport(prev => (prev ? { ...prev, ai_review: null } : prev));
      showStoredReview(null);
      toast('AI review stopped', 'info');
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not stop the AI review'), 'error');
      // It may have finished in the meantime, so show its current state.
      await loadReport();
    } finally {
      setStopping(false);
    }
  };

  const closeReview = async () => {
    showStoredReview(null);
    setReport(prev => (prev ? { ...prev, ai_review: null } : prev));
    try {
      await apiService.clearReportReview(reportId);
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not close the AI review'), 'error');
    }
  };

  // Accepting and undoing return the report's results and review as the server left them.
  const showReviewResponse = (response: ReviewActionResponse) => {
    setTestResults(response.test_results);
    setReport(prev => (prev ? { ...prev, ai_review: response.review } : prev));
    showStoredReview(response.review);
    if (editingId !== null && !response.test_results.some(result => result.id === editingId)) cancelEdit();
  };

  const acceptSuggestions = async (ids: number[], busy: 'all' | number) => {
    setApplying(busy);
    try {
      const response = await apiService.acceptReviewSuggestions(reportId, ids);
      showReviewResponse(response);
      const count = response.applied?.length ?? 0;
      if (count === 0) toast('These suggestions no longer apply', 'info');
      else if (ids.length > 1) toast(`Applied ${count} suggestion${count === 1 ? '' : 's'}`, 'success');
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not apply the suggestions'), 'error');
    } finally {
      setApplying(null);
    }
  };

  const undoChange = async (appliedId: number) => {
    setUndoingId(appliedId);
    try {
      showReviewResponse(await apiService.undoReviewChange(reportId, appliedId));
      toast('Change undone', 'success');
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not undo this change'), 'error');
    } finally {
      setUndoingId(null);
    }
  };

  const exportCSV = () => {
    if (!report || testResults.length === 0) {
      toast('No test results to export', 'info');
      return;
    }
    const headers = 'Test Name,Value,Unit,Reference Range,Status';
    const rows = testResults.map(tr =>
      `"${tr.test_name}",${tr.value},"${tr.unit}","${tr.reference_range}",${tr.status}`
    );
    const blob = new Blob([[headers, ...rows].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${report.title.replace(/[^a-zA-Z0-9]/g, '_')}_results.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /**
   * The whole report as JSON: what it is, every result, and the text as printed. Unlike what the chat
   * sends, nothing is redacted here — it is the user's own report, going wherever they choose to put it.
   */
  const reportJSON = () => {
    const text = (report?.parsed_data as { text?: unknown } | undefined)?.text;
    return JSON.stringify(
      {
        report: {
          id: report?.id,
          title: report?.title,
          report_type: report?.report_type,
          lab_name: report?.lab_name || null,
          report_date: report?.report_date,
          notes: report?.notes || null,
        },
        results: testResults.map(tr => ({
          test_name: tr.test_name,
          catalog_test: tr.test_type_name ?? null,
          value: tr.value,
          unit: tr.unit || null,
          reference_range: tr.reference_range || null,
          status: tr.status || null,
          notes: tr.notes || null,
        })),
        report_text: typeof text === 'string' && text.trim() ? text : null,
        exported_at: new Date().toISOString(),
      },
      null,
      2,
    );
  };

  const exportJSON = () => {
    if (!report) return;
    downloadText(reportJSON(), `${report.title.replace(/[^a-zA-Z0-9]/g, '_')}_report.json`);
  };

  const copyJSON = async () => {
    if (!report) return;
    const copied = await copyText(reportJSON());
    toast(
      copied ? 'Report JSON copied' : 'Could not reach the clipboard — use Export JSON instead',
      copied ? 'success' : 'error',
    );
  };

  const describeSuggestion = (item: PendingSuggestion) => {
    if (item.action === 'add') {
      const { test_name, value, unit, reference_range } = item.result;
      return (
        <>
          <strong>{test_name}</strong> {value} {unit}
          {reference_range && <span style={{ color: 'var(--text-muted)' }}> (ref {reference_range})</span>}{' '}
          <span className={`badge ${item.catalog_name ? 'badge-success' : 'badge-warning'}`}>
            {item.catalog_name ? 'Catalog' : 'Custom'}
          </span>
        </>
      );
    }
    const row = testResults.find(r => r.id === item.result_id);
    if (!row) return <span style={{ color: 'var(--text-muted)' }}>This result no longer exists.</span>;
    if (item.action === 'remove') {
      return <><strong>{row.test_name}</strong> {row.value} {row.unit}</>;
    }
    return (
      <>
        <strong>{row.test_name}</strong>
        {Object.entries(item.changes).map(([field, value]) => (
          <span key={field} style={{ display: 'block', fontSize: 'var(--font-sm)' }}>
            {FIELD_LABELS[field] ?? field}:{' '}
            <span style={{ color: 'var(--text-muted)', textDecoration: 'line-through' }}>
              {String(row[field as keyof TestResult] ?? '') || '—'}
            </span>{' '}
            → {value || '—'}
          </span>
        ))}
      </>
    );
  };

  const describeChange = (change: AppliedReviewChange) => {
    if (change.action !== 'update') {
      const { test_name, value, unit } = change.result;
      return <>{change.action === 'remove' ? 'Removed' : 'Added'} <strong>{test_name}</strong> {value} {unit}</>;
    }
    const row = testResults.find(r => r.id === change.result_id);
    return (
      <>
        <strong>{row?.test_name ?? change.before.test_name ?? 'Result'}</strong>
        {Object.entries(change.changes).map(([field, value]) => (
          <span key={field} style={{ display: 'block', fontSize: 'var(--font-sm)' }}>
            {FIELD_LABELS[field] ?? field}:{' '}
            <span style={{ color: 'var(--text-muted)' }}>
              {String(change.before[field as keyof typeof change.before] ?? '') || '—'}
            </span>{' '}
            → {value || '—'}
          </span>
        ))}
      </>
    );
  };

  if (loading) {
    return (
      <div className="stack">
        <div className="skeleton" style={{ height: 48, width: 280 }} />
        <div className="skeleton" style={{ height: 200 }} />
        <div className="skeleton" style={{ height: 320 }} />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="empty-state card">
        <div className="empty-state-title">Report not found</div>
        <div className="empty-state-text">This report may have been deleted or you do not have access.</div>
        <Link to={reportListPath()} className="btn btn-secondary">Back to reports</Link>
      </div>
    );
  }

  // Follow the report list as it was last shown (search, sort, filter); otherwise the default list order.
  const neighbors = listedReportNeighbors(report.id) ?? report.neighbors ?? null;
  const parsing = isReportParsing(report.status);
  // The text the parser read, when it read any: a scanned report often has results and no text layer.
  const reportText = String((report.parsed_data as { text?: unknown } | undefined)?.text ?? '').trim();
  // What the AI can be asked about is what the report actually holds, not whether the parser found rows:
  // `is_parsed` is set once, at parse time, so a report whose results were added afterwards by the AI
  // review or by hand still reads as unparsed.
  const canAskAI = !parsing && (testResults.length > 0 || reportText.length > 0);
  const appliedChanges = review?.applied ?? [];

  return (
    <div className="stack animate-fade-in">
      <div className="page-header">
        <div>
          <Link to={reportListPath()} className="eyebrow" style={{ display: 'inline-block', marginBottom: 'var(--space-2)' }}>
            ← Medical reports
          </Link>
          <h1 className="page-title">{report.title}</h1>
          <p className="page-subtitle">
            {report.lab_name && `${report.lab_name} · `}
            {REPORT_TYPES[report.report_type] || report.report_type} ·{' '}
            <span className="font-mono">{new Date(`${report.report_date}T00:00:00`).toLocaleDateString()}</span>
          </p>
        </div>
        <div className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {neighbors && neighbors.total > 1 && (
            <div className="row" role="group" aria-label="Move between reports" style={{ gap: 'var(--space-2)' }}>
              {neighbors.previous ? (
                <Link
                  to={`/medical-reports/${neighbors.previous.id}`}
                  className="btn btn-secondary btn-sm"
                  title={neighbors.previous.title}
                >
                  ← Previous
                </Link>
              ) : (
                <button type="button" className="btn btn-secondary btn-sm" disabled>← Previous</button>
              )}
              <span className="font-mono form-hint">{neighbors.position} / {neighbors.total}</span>
              {neighbors.next ? (
                <Link
                  to={`/medical-reports/${neighbors.next.id}`}
                  className="btn btn-secondary btn-sm"
                  title={neighbors.next.title}
                >
                  Next →
                </Link>
              ) : (
                <button type="button" className="btn btn-secondary btn-sm" disabled>Next →</button>
              )}
            </div>
          )}
          {canAskAI && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={toggleChat} aria-pressed={showChat}>
              {showChat ? 'Hide AI chat' : 'Chat with AI'}
            </button>
          )}
          {report.file && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={togglePdf} aria-pressed={showPdf}>
              {showPdf ? 'Hide PDF' : 'Compare with PDF'}
            </button>
          )}
          {report.file && (
            <a href={report.file} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm">
              Download file
            </a>
          )}
          {testResults.length > 0 && (
            <button className="btn btn-secondary btn-sm" onClick={exportCSV}>Export CSV</button>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={exportJSON}
            title="The report and its results as JSON, including the text as printed"
          >
            Export JSON
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={copyJSON}
            title="Copy the same JSON, to paste somewhere else"
          >
            Copy JSON
          </button>
          <button className="btn btn-danger btn-sm" onClick={() => navigate(reportListPath())}>
            Close
          </button>
        </div>
      </div>

      <div className="report-section">
        <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-4)' }}>
          <div>
            <p className="eyebrow">Parse status</p>
            <div className="row" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
              <span className={`badge ${statusBadgeClass(report.status, report.is_parsed)}`}>
                {statusLabel(report.status, report.is_parsed)}
              </span>
              {parsing && (
                <span className="row" style={{ gap: 'var(--space-2)', color: 'var(--text-muted)', fontSize: 'var(--font-sm)' }}>
                  <span className="spinner" /> Parsing in background…
                </span>
              )}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p className="eyebrow">Results</p>
            <div className="stat-value" style={{ fontSize: 'var(--font-2xl)', color: 'var(--teal)' }}>
              {testResults.length}
            </div>
            <div className="stat-label">test values</div>
          </div>
        </div>

        {(report.parse_error || (report.parsed_data?.error as string)) && (
          <div className="alert alert-error" style={{ marginTop: 'var(--space-5)' }}>
            {report.parse_error || String(report.parsed_data?.error)}
          </div>
        )}
      </div>

      {parsing && testResults.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 'var(--space-10)' }}>
          <span className="spinner spinner-lg" style={{ margin: '0 auto var(--space-4)' }} />
          <p style={{ color: 'var(--text-secondary)' }}>
            Extracting lab values from your report. This can take a few minutes for scanned PDFs.
          </p>
          <p className="font-mono" style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
            Status updates every 5 seconds
          </p>
        </div>
      ) : (
        <div className={showPdf || showChat ? 'report-compare' : undefined}>
          <div className="stack">
            {report.ai_review?.status === 'pending' && (
              <div className="card row" style={{ gap: 'var(--space-3)' }}>
                <span className="spinner" />
                <span style={{ color: 'var(--text-secondary)', flex: 1 }}>
                  {report.ai_review.started_at ? 'AI review in progress.' : 'AI review queued behind other reports.'} Its
                  results appear here when it finishes.
                </span>
                <button type="button" className="btn btn-secondary btn-sm" onClick={stopReview} disabled={stopping}>
                  {stopping ? 'Stopping…' : 'Stop'}
                </button>
              </div>
            )}

            {report.ai_review?.status === 'failed' && (
              <div className="alert alert-error row-between" style={{ gap: 'var(--space-3)' }}>
                <span>AI review failed: {report.ai_review.error}</span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={closeReview}>Dismiss</button>
              </div>
            )}

            {review && (
              <div className="card">
                <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
                  <div>
                    <h3 style={{ fontSize: 'var(--font-lg)' }}>AI review</h3>
                    <p className="font-mono" style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)' }}>
                      {review.model} · {REVIEW_INPUT_LABELS[review.input_mode] ?? 'PDF text'}
                      {review.parts > 1 && ` · reviewed in ${review.parts} parts`}
                    </p>
                  </div>
                  <div className="row" style={{ gap: 'var(--space-2)' }}>
                    {pending.length > 1 && (
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => acceptSuggestions(pending.map(item => item.uid), 'all')}
                        disabled={applying !== null}
                      >
                        {applying === 'all' ? 'Applying…' : 'Accept all'}
                      </button>
                    )}
                    <button type="button" className="btn btn-ghost btn-sm" onClick={closeReview}>
                      Close
                    </button>
                  </div>
                </div>
                {review.summary && <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>{review.summary}</p>}
                {review.failed_parts.length > 0 && (
                  <div className="alert alert-error" style={{ marginBottom: 'var(--space-3)' }}>
                    {review.failed_parts.map(part => {
                      const single = part.first_page === part.last_page;
                      return (
                        <div key={part.part}>
                          {single ? `Page ${part.first_page} was` : `Pages ${part.first_page}–${part.last_page} were`} not
                          reviewed: {part.error} Check {single ? 'that page' : 'those pages'} yourself.
                        </div>
                      );
                    })}
                  </div>
                )}
                {pending.length === 0 ? (
                  <p className="form-hint">
                    {(review.applied ?? []).length === 0 ? 'The AI found nothing to change in these results.' : 'No suggestions left to review.'}
                  </p>
                ) : (
                  <div>
                    {pending.map(item => (
                      <div key={item.uid} className="review-suggestion">
                        <div style={{ minWidth: 0 }}>
                          <span
                            className={`badge ${item.action === 'add' ? 'badge-success' : item.action === 'remove' ? 'badge-danger' : 'badge-warning'}`}
                            style={{ marginRight: 'var(--space-2)' }}
                          >
                            {item.action === 'add' ? 'Add' : item.action === 'remove' ? 'Remove' : 'Fix'}
                          </span>
                          {describeSuggestion(item)}
                          {item.reason && <div className="form-hint">{item.reason}</div>}
                        </div>
                        <div className="row" style={{ gap: 'var(--space-1)', flexShrink: 0 }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => acceptSuggestions([item.uid], item.uid)}
                            disabled={applying !== null}
                          >
                            {applying === item.uid ? 'Applying…' : 'Accept'}
                          </button>
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => dismissSuggestion(item.uid)}>
                            Dismiss
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {appliedChanges.length > 0 && (
                  <div style={{ marginTop: 'var(--space-4)' }}>
                    <p className="eyebrow" style={{ marginBottom: 'var(--space-2)' }}>Applied</p>
                    {appliedChanges.map(change => (
                      <div key={change.id} className="review-suggestion">
                        <div style={{ minWidth: 0 }}>
                          <span
                            className={`badge ${change.automatic ? 'badge-muted' : 'badge-success'}`}
                            style={{ marginRight: 'var(--space-2)' }}
                          >
                            {change.automatic ? 'Auto' : 'Accepted'}
                          </span>
                          {describeChange(change)}
                          {change.reason && <div className="form-hint">{change.reason}</div>}
                        </div>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => undoChange(change.id)}
                          disabled={undoingId !== null}
                        >
                          {undoingId === change.id ? 'Undoing…' : 'Undo'}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="card">
              <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
                <h3 style={{ fontSize: 'var(--font-lg)' }}>Test results</h3>
                <div className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  {reviewAvailable && (
                    <>
                      <label
                        className="row form-hint"
                        style={{ gap: 'var(--space-1)', cursor: ocrAvailable ? 'pointer' : 'not-allowed' }}
                        title={
                          ocrAvailable
                            ? 'Read the pages with the Report OCR model and review against that text, for PDFs whose text parses badly'
                            : 'Set up Report OCR in AI settings to use this'
                        }
                      >
                        <input
                          type="checkbox"
                          style={reviewOptionCheckbox}
                          checked={reviewWithOcr && ocrAvailable}
                          disabled={!ocrAvailable || reviewing || reviewRunning}
                          onChange={e => setReviewWithOcr(e.target.checked)}
                        />
                        OCR text
                      </label>
                      <label
                        className="row form-hint"
                        style={{ gap: 'var(--space-1)', cursor: 'pointer' }}
                        title="Send the page images to the review model, which must accept images"
                      >
                        <input
                          type="checkbox"
                          style={reviewOptionCheckbox}
                          checked={reviewWithImages}
                          disabled={reviewing || reviewRunning}
                          onChange={e => setReviewWithImages(e.target.checked)}
                        />
                        Page images
                      </label>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={runReview} disabled={reviewing || reviewRunning}>
                        {reviewing || reviewRunning ? <><span className="spinner" /> Reviewing…</> : 'AI review'}
                      </button>
                    </>
                  )}
                  {!adding && (
                    <button type="button" className="btn btn-primary btn-sm" onClick={openAddForm}>
                      Add result
                    </button>
                  )}
                </div>
              </div>

              {adding && (
                <form className="report-add-form" onSubmit={saveNewResult}>
                  <div className="report-add-grid">
                    <div className="form-group">
                      <label className="form-label" htmlFor="new-result-name">Test</label>
                      <input
                        id="new-result-name"
                        className="form-input"
                        list="catalog-test-names"
                        placeholder="Search the catalog or type a new test"
                        autoComplete="off"
                        value={newResult.test_name}
                        onChange={e => setNewResult({ ...newResult, test_name: e.target.value })}
                        autoFocus
                        required
                      />
                      <datalist id="catalog-test-names">
                        {catalog.map(type => (
                          <option key={type.id} value={type.display_name}>{type.category}</option>
                        ))}
                      </datalist>
                    </div>
                    <div className="form-group">
                      <label className="form-label" htmlFor="new-result-value">Value</label>
                      <input
                        id="new-result-value"
                        className="form-input"
                        value={newResult.value}
                        onChange={e => setNewResult({ ...newResult, value: e.target.value })}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label" htmlFor="new-result-unit">Unit</label>
                      <input
                        id="new-result-unit"
                        className="form-input"
                        list="new-result-units"
                        autoComplete="off"
                        value={newResult.unit}
                        onChange={e => setNewResult({ ...newResult, unit: e.target.value })}
                      />
                      <datalist id="new-result-units">
                        {newResultUnits.map(u => (
                          <option key={u.id} value={u.unit.symbol || u.unit.name}>{u.unit.display_name}</option>
                        ))}
                      </datalist>
                    </div>
                    <div className="form-group">
                      <label className="form-label" htmlFor="new-result-range">Reference range</label>
                      <input
                        id="new-result-range"
                        className="form-input"
                        placeholder="e.g. 13.0 - 17.0"
                        value={newResult.reference_range}
                        onChange={e => setNewResult({ ...newResult, reference_range: e.target.value })}
                      />
                    </div>
                  </div>
                  <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
                    <span className="form-hint">
                      {newResult.test_name.trim() &&
                        (matchedType ? (
                          <><span className="badge badge-success">Catalog</span> {matchedType.display_name}: status is checked against its reference range.</>
                        ) : (
                          <><span className="badge badge-warning">Custom</span> Not in the catalog yet. Saved as typed, without unit conversion or range checks.</>
                        ))}
                    </span>
                    <div className="row" style={{ gap: 'var(--space-2)' }}>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={closeAddForm}>Cancel</button>
                      <button type="submit" className="btn btn-primary btn-sm" disabled={savingNew}>
                        {savingNew ? 'Saving…' : 'Save result'}
                      </button>
                    </div>
                  </div>
                </form>
              )}

              {testResults.length === 0 ? (
                <div className="empty-state" style={{ padding: 'var(--space-6)' }}>
                  <div className="empty-state-title">No test results</div>
                  <div className="empty-state-text">
                    {report.status === 'FAILED'
                      ? 'Parsing did not extract any values. Add results manually, run an AI review, or re-upload a clearer PDF.'
                      : 'No lab values were found in this report. Add them manually or run an AI review.'}
                  </div>
                </div>
              ) : (
                <div className="table-wrapper">
                  <table>
                    <thead>
                      <tr>
                        <th>Test</th>
                        <th>Value</th>
                        <th>Unit</th>
                        <th>Reference</th>
                        <th>Status</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {testResults.map(result => {
                        const isEditing = editingId === result.id;
                        const isCustom = !result.test_type_name;
                        // A result without a number ("Absent", "Reactive") is kept as text and never joins a catalog trend.
                        const isTextResult = Boolean(result.value?.trim()) && !/^\s*(?:[<>]=?|≤|≥)?\s*[-+]?\d/.test(result.value);
                        const altUnits = editUnits
                          .map(u => u.unit.name)
                          .filter(name => name && name !== result.unit);

                        return (
                          <tr
                            key={result.id}
                            id={`report-result-${result.id}`}
                            className={result.id === resultId ? 'report-result-target' : undefined}
                          >
                            <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                              {result.test_name}
                              {isCustom && (
                                <span
                                  className="badge badge-muted"
                                  style={{ marginLeft: 'var(--space-2)' }}
                                  title={
                                    isTextResult
                                      ? 'A result without a number, such as “Absent”, is kept as text: it is not linked to a catalog test or charted in Health Trends'
                                      : 'Not in the lab test catalog'
                                  }
                                >
                                  {isTextResult ? 'Text' : 'Custom'}
                                </span>
                              )}
                            </td>
                            <td>
                              {isEditing ? (
                                <input
                                  className="form-input"
                                  style={{ width: 88, padding: 'var(--space-1) var(--space-2)' }}
                                  value={editForm.value}
                                  onChange={e => setEditForm({ ...editForm, value: e.target.value })}
                                />
                              ) : (
                                <span className="font-mono">{result.value}</span>
                              )}
                            </td>
                            <td>
                              {isEditing ? (
                                <select
                                  className="form-select"
                                  style={{ width: 120, padding: 'var(--space-1) var(--space-2)' }}
                                  value={editForm.unit}
                                  onChange={e => setEditForm({ ...editForm, unit: e.target.value })}
                                >
                                  <option value={editForm.unit}>{editForm.unit || 'Unit'}</option>
                                  {editUnits.map(u => (
                                    <option key={u.id} value={u.unit.name}>{u.unit.display_name || u.unit.name}</option>
                                  ))}
                                </select>
                              ) : (
                                result.unit
                              )}
                            </td>
                            <td>
                              {isEditing ? (
                                <input
                                  className="form-input"
                                  style={{ width: 100, padding: 'var(--space-1) var(--space-2)' }}
                                  value={editForm.reference_range}
                                  onChange={e => setEditForm({ ...editForm, reference_range: e.target.value })}
                                />
                              ) : (
                                result.reference_range
                              )}
                            </td>
                            <td>
                              {result.status && (
                                <span className={`badge ${testResultBadgeClass(result.status)}`}>{result.status}</span>
                              )}
                            </td>
                            <td>
                              <div className="row" style={{ gap: 'var(--space-1)', justifyContent: 'flex-end' }}>
                                {isEditing ? (
                                  <>
                                    <button type="button" className="btn btn-primary btn-sm" onClick={() => saveEdit(result.id)}>Save</button>
                                    <button type="button" className="btn btn-ghost btn-sm" onClick={cancelEdit}>Cancel</button>
                                  </>
                                ) : (
                                  <>
                                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => startEdit(result)}>Edit</button>
                                    {!isCustom && (
                                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => validateResult(result.id)}>Validate</button>
                                    )}
                                    <button
                                      type="button"
                                      className="btn btn-ghost btn-sm"
                                      style={{ color: 'var(--danger, #b42318)' }}
                                      onClick={() => deleteResult(result)}
                                      aria-label={`Delete ${result.test_name}`}
                                    >
                                      Delete
                                    </button>
                                    {!isCustom && altUnits.length > 0 && (
                                      <select
                                        className="form-select"
                                        style={{ width: 72, padding: '2px 4px', fontSize: 'var(--font-xs)' }}
                                        value=""
                                        disabled={convertingId === result.id}
                                        onChange={e => {
                                          if (e.target.value) convertUnit(result.id, e.target.value);
                                          e.target.value = '';
                                        }}
                                      >
                                        <option value="">Convert</option>
                                        {altUnits.map(u => (
                                          <option key={u} value={u}>{u}</option>
                                        ))}
                                      </select>
                                    )}
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {showPdf && (
            <div className="card report-compare-pdf">
              {pdfError ? (
                <div className="alert alert-error">{pdfError}</div>
              ) : pdfUrl ? (
                <iframe className="report-pdf-frame" src={pdfUrl} title="Original report PDF" />
              ) : (
                <div className="skeleton report-pdf-frame" />
              )}
            </div>
          )}

          {showChat && (
            <div className="report-compare-chat">
              <AIChatPanel
                subject="report"
                id={report.id}
                hasRows={testResults.length > 0}
                onClose={() => setShowChat(false)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/** Each report gets a fresh page, so edits, the PDF, and the review of the previous report do not carry over. */
const ReportDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  return <ReportDetailPage key={id} />;
};

export default ReportDetail;
