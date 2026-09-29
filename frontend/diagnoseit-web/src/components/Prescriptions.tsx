import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiService, PRESCRIPTION_FILE_ACCEPT } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import type { Prescription } from '../services/api';
import { apiErrorMessage } from '../utils/apiErrors';
import { parseDateInput, todayIsoDate } from '../utils/dates';
import { saveListSort, savedListSort } from '../utils/reportList';
import {
  isReportParsing, reportMatchesFilter, statusBadgeClass, statusLabel, type ReportStatusFilter,
} from '../utils/reportStatus';
import { IconSearch } from './Icons';
import AIChatPanel from './AIChatPanel';
import MedicationList from './MedicationList';
import PrescriptionReview from './PrescriptionReview';
import DateTextInput from './DateTextInput';
import { IconPrescriptions, IconClose, IconTrash } from './Icons';

const REVIEW_OPTION_CHECKBOX: React.CSSProperties = {
  width: 18, height: 18, margin: 0, accentColor: 'var(--teal)',
};

const STATUS_FILTERS: { key: ReportStatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'parsed', label: 'Parsed' },
  { key: 'processing', label: 'Processing' },
  { key: 'failed', label: 'Failed' },
];

type PrescriptionSort =
  | 'date_desc' | 'date_asc' | 'added_desc' | 'added_asc' | 'doctor_asc' | 'doctor_desc';

const SORT_OPTIONS: { value: PrescriptionSort; label: string }[] = [
  { value: 'date_desc', label: 'Prescription date, newest first' },
  { value: 'date_asc', label: 'Prescription date, oldest first' },
  { value: 'added_desc', label: 'Date added, newest first' },
  { value: 'added_asc', label: 'Date added, oldest first' },
  { value: 'doctor_asc', label: 'Doctor, A to Z' },
  { value: 'doctor_desc', label: 'Doctor, Z to A' },
];
const DEFAULT_SORT: PrescriptionSort = 'date_desc';

const byDoctor = (a: Prescription, b: Prescription) =>
  (a.doctor_name || '').localeCompare(b.doctor_name || '', undefined, { numeric: true, sensitivity: 'base' });
const byDate = (a: Prescription, b: Prescription) =>
  a.prescription_date.localeCompare(b.prescription_date) || a.created_at.localeCompare(b.created_at);
const byAdded = (a: Prescription, b: Prescription) => a.created_at.localeCompare(b.created_at);

const SORTERS: Record<PrescriptionSort, (a: Prescription, b: Prescription) => number> = {
  date_desc: (a, b) => byDate(b, a),
  date_asc: byDate,
  added_desc: (a, b) => byAdded(b, a),
  added_asc: byAdded,
  doctor_asc: byDoctor,
  doctor_desc: (a, b) => byDoctor(b, a),
};

/**
 * Every word of the query appears somewhere in the prescription, ignoring case.
 *
 * The medicines are searched too: what someone remembers about a prescription is usually the medicine on
 * it, not the doctor who wrote it.
 */
function matchesQuery(prescription: Prescription, query: string): boolean {
  const medicines = (prescription.medications ?? [])
    .map(medication => `${medication.medication_name} ${medication.dosage ?? ''}`)
    .join(' ');
  const haystack = [
    prescription.doctor_name, prescription.hospital_clinic, prescription.notes, medicines,
  ].join(' ').toLocaleLowerCase();
  return query.toLocaleLowerCase().split(/\s+/).filter(Boolean).every(word => haystack.includes(word));
}

const Prescriptions: React.FC = () => {
  const { toast, confirm } = useToast();
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  // Search, sort, and status filter live in the address, so a link to the list keeps them.
  const [searchParams, setSearchParams] = useSearchParams();
  const nameQuery = searchParams.get('q') ?? '';
  // Without a sort in the address, the last one chosen here is used.
  const sort =
    SORT_OPTIONS.find(option => option.value === (searchParams.get('sort') ?? savedListSort('prescriptions')))?.value
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
    [setSearchParams],
  );
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [chatId, setChatId] = useState<number | null>(null);
  const [originalId, setOriginalId] = useState<number | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [originalType, setOriginalType] = useState('');
  const [originalError, setOriginalError] = useState('');
  const originalUrlRef = useRef<string | null>(null);
  const originalRequestRef = useRef(0);
  const [rereading, setRereading] = useState<number | null>(null);
  const [error, setError] = useState('');

  const replaceOriginalUrl = useCallback((url: string | null) => {
    if (originalUrlRef.current) URL.revokeObjectURL(originalUrlRef.current);
    originalUrlRef.current = url;
    setOriginalUrl(url);
  }, []);

  const closeOriginal = useCallback(() => {
    originalRequestRef.current += 1;
    setOriginalId(null);
    setOriginalType('');
    setOriginalError('');
    replaceOriginalUrl(null);
  }, [replaceOriginalUrl]);

  // Release private prescription data when the page closes.
  useEffect(() => () => {
    originalRequestRef.current += 1;
    if (originalUrlRef.current) URL.revokeObjectURL(originalUrlRef.current);
  }, []);

  const toggleOriginal = async (prescription: Prescription) => {
    if (originalId === prescription.id) {
      closeOriginal();
      return;
    }

    const request = originalRequestRef.current + 1;
    originalRequestRef.current = request;
    replaceOriginalUrl(null);
    setOriginalId(prescription.id);
    setOriginalType('');
    setOriginalError('');
    setExpandedId(prescription.id);
    setChatId(null);

    try {
      const blob = await apiService.getPrescriptionFile(prescription.id);
      const url = URL.createObjectURL(blob);
      if (originalRequestRef.current !== request) {
        URL.revokeObjectURL(url);
        return;
      }
      originalUrlRef.current = url;
      setOriginalUrl(url);
      setOriginalType(blob.type);
    } catch {
      if (originalRequestRef.current === request) {
        setOriginalError('Could not load the original prescription.');
      }
    }
  };

  const fetchPrescriptions = useCallback(async (silent = false) => {
    try {
      setPrescriptions(await apiService.getPrescriptions());
      setError('');
    } catch (err) {
      if (!silent) setError(apiErrorMessage(err, 'Failed to load prescriptions'));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPrescriptions(); }, [fetchPrescriptions]);

  // Reading and reviewing both run on a worker, so the page follows them the way the report list does.
  const busyIds = prescriptions
    .filter(rx => isReportParsing(rx.status) || rx.ai_review?.status === 'pending')
    .map(rx => rx.id);
  const busyKey = busyIds.join(',');
  useEffect(() => {
    if (!busyKey) return;
    const timer = setInterval(async () => {
      const done = await Promise.all(
        busyKey.split(',').map(async id => {
          try {
            const state = await apiService.getPrescriptionStatus(Number(id));
            return !isReportParsing(state.status) && state.ai_review_status !== 'pending';
          } catch {
            return false;
          }
        }),
      );
      if (done.some(Boolean)) fetchPrescriptions(true);
    }, 5000);
    return () => clearInterval(timer);
  }, [busyKey, fetchPrescriptions]);

  const [reviewing, setReviewing] = useState<number | null>(null);
  // Per-prescription choice of whether the review also looks at the original page.
  const [withImages, setWithImages] = useState<Record<number, boolean>>({});

  /** Checking OCR text against itself confirms its mistakes, so a photo or a scan starts with this on. */
  const imagesDefault = (rx: Prescription) => {
    const source = (rx.parsed_data as { text_source?: unknown } | undefined)?.text_source;
    return source === 'photo' || source === 'ocr';
  };
  const imagesFor = (rx: Prescription) => withImages[rx.id] ?? imagesDefault(rx);

  const runReview = async (id: number, images: boolean) => {
    setReviewing(id);
    try {
      await apiService.reviewPrescriptionWithAI(id, { images });
      setExpandedId(id);
      toast('AI review queued', 'success');
      fetchPrescriptions(true);
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not start the AI review'), 'error');
    } finally {
      setReviewing(null);
    }
  };

  const statusCounts = useMemo(
    () => Object.fromEntries(
      STATUS_FILTERS.map(({ key }) => [key, prescriptions.filter(rx => reportMatchesFilter(rx, key)).length]),
    ) as Record<ReportStatusFilter, number>,
    [prescriptions],
  );

  const shown = useMemo(
    () => prescriptions
      .filter(rx => reportMatchesFilter(rx, statusFilter) && matchesQuery(rx, nameQuery))
      .sort(SORTERS[sort]),
    [prescriptions, statusFilter, nameQuery, sort],
  );

  const reread = async (id: number) => {
    setRereading(id);
    try {
      await apiService.reparsePrescription(id);
      toast('Reading this prescription again…', 'success');
      fetchPrescriptions(true);
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not read this prescription again'), 'error');
    } finally {
      setRereading(null);
    }
  };

  const handleDelete = async (id: number) => {
    const ok = await confirm('Delete this prescription?');
    if (!ok) return;
    try {
      await apiService.deletePrescription(id);
      setPrescriptions(prev => prev.filter(p => p.id !== id));
      if (originalId === id) closeOriginal();
      toast('Prescription deleted', 'success');
    } catch { toast('Failed to delete', 'error'); }
  };

  if (loading) {
    return (
      <div className="stack">
        <div className="skeleton" style={{ height: 48, width: 220 }} />
        {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 100 }} />)}
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Prescriptions</h1>
          <p className="page-subtitle">Manage your medication prescriptions</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowUpload(true)}>Add prescription</button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 'var(--space-4)' }}>{error}</div>}

      {prescriptions.length > 0 && (
        <div className="row-between" style={{ marginBottom: 'var(--space-6)', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <div className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            {STATUS_FILTERS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                className={`btn btn-sm ${statusFilter === key ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => updateParam('status', key === 'all' ? '' : key)}
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
                placeholder="Search by doctor, clinic, or medicine"
                aria-label="Search prescriptions by doctor, clinic, or medicine"
              />
            </div>
            <select
              className="form-select"
              style={{ width: 'auto' }}
              value={sort}
              onChange={e => {
                saveListSort('prescriptions', e.target.value);
                updateParam('sort', e.target.value === DEFAULT_SORT ? '' : e.target.value);
              }}
              aria-label="Sort prescriptions"
            >
              {SORT_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {nameQuery.trim() && shown.length > 0 && (
        <p className="form-hint" style={{ marginTop: 'calc(-1 * var(--space-4))', marginBottom: 'var(--space-4)' }}>
          {shown.length} of {statusCounts[statusFilter]} prescription{statusCounts[statusFilter] === 1 ? '' : 's'}{' '}
          match “{nameQuery.trim()}”
        </p>
      )}

      {prescriptions.length > 0 && shown.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-state-icon"><IconPrescriptions size={32} /></div>
          <div className="empty-state-title">Nothing matches</div>
          <div className="empty-state-text">
            No prescription matches this search and filter. Clear them to see all {prescriptions.length}.
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
          >
            Clear search and filter
          </button>
        </div>
      ) : prescriptions.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-state-icon"><IconPrescriptions size={32} /></div>
          <div className="empty-state-title">No prescriptions</div>
          <div className="empty-state-text">Upload your prescriptions to keep track of medications</div>
          <button className="btn btn-primary" onClick={() => setShowUpload(true)}>Add Prescription</button>
        </div>
      ) : (
        <div className="stack stagger-children">
          {shown.map(rx => (
            <div key={rx.id} className="card" style={{ cursor: 'pointer' }}
              onClick={() => setExpandedId(expandedId === rx.id ? null : rx.id)}>
              <div className="row-between">
                <div>
                  <div style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>
                    {rx.doctor_name ? `Dr. ${rx.doctor_name}` : 'Prescription'}
                  </div>
                  <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                    {rx.hospital_clinic && `${rx.hospital_clinic} · `}
                    {new Date(`${rx.prescription_date}T00:00:00`).toLocaleDateString()}
                  </div>
                  {rx.notes && (
                    <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginTop: 'var(--space-2)' }}>
                      {rx.notes}
                    </p>
                  )}
                </div>
                <div className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <span className={`badge ${statusBadgeClass(rx.status, rx.is_parsed)}`}>
                    {statusLabel(rx.status, rx.is_parsed)}
                  </span>
                  {isReportParsing(rx.status) && <span className="spinner" aria-label="Reading" />}
                  {rx.file && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={e => { e.stopPropagation(); toggleOriginal(rx); }}
                      aria-pressed={originalId === rx.id}
                    >
                      {originalId === rx.id ? 'Hide original' : 'Compare with original'}
                    </button>
                  )}
                  {!isReportParsing(rx.status) && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={e => {
                        e.stopPropagation();
                        const opening = chatId !== rx.id;
                        setChatId(opening ? rx.id : null);
                        if (opening) {
                          closeOriginal();
                          setExpandedId(rx.id);
                        }
                      }}
                      aria-pressed={chatId === rx.id}
                    >
                      {chatId === rx.id ? 'Hide AI chat' : 'Chat with AI'}
                    </button>
                  )}
                  {!isReportParsing(rx.status) && rx.ai_review?.status !== 'pending' && (
                    <>
                      <label
                        className="row form-hint"
                        style={{ gap: 'var(--space-1)', cursor: 'pointer' }}
                        title="Send the original page to the review model as a picture, so it can check what OCR read"
                        onClick={e => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          style={REVIEW_OPTION_CHECKBOX}
                          checked={imagesFor(rx)}
                          disabled={reviewing === rx.id}
                          onChange={e => setWithImages({ ...withImages, [rx.id]: e.target.checked })}
                        />
                        Page images
                      </label>
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={reviewing === rx.id}
                        onClick={e => { e.stopPropagation(); runReview(rx.id, imagesFor(rx)); }}
                        title="Check the medicines against the prescription itself"
                      >
                        {reviewing === rx.id ? 'Starting…' : 'AI review'}
                      </button>
                    </>
                  )}
                  {!isReportParsing(rx.status) && (
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={rereading === rx.id}
                      onClick={e => { e.stopPropagation(); reread(rx.id); }}
                      title="Read this prescription again, for example after setting up the OCR model"
                    >
                      {rereading === rx.id ? 'Reading…' : 'Read again'}
                    </button>
                  )}
                  <button className="btn btn-danger btn-sm"
                    onClick={e => { e.stopPropagation(); handleDelete(rx.id); }}>
                    <IconTrash size={14} />
                  </button>
                </div>
              </div>

              {rx.parse_error && (
                <div className="alert alert-error" style={{ marginTop: 'var(--space-4)' }} onClick={e => e.stopPropagation()}>
                  {rx.parse_error}
                </div>
              )}

              {(expandedId === rx.id || chatId === rx.id || originalId === rx.id || rx.ai_review?.status === 'pending') && (
                <div
                  className={chatId === rx.id || originalId === rx.id ? 'report-compare' : undefined}
                  style={{ animation: 'slideUp 0.3s ease' }}
                  onClick={e => e.stopPropagation()}
                >
                  <div>
                    {rx.ai_review && (
                      <PrescriptionReview
                        prescriptionId={rx.id}
                        review={rx.ai_review}
                        onChanged={() => fetchPrescriptions(true)}
                      />
                    )}
                    {rx.medications && rx.medications.length > 0 ? (
                      <MedicationList
                        prescriptionId={rx.id}
                        medications={rx.medications}
                        onChanged={() => fetchPrescriptions(true)}
                      />
                    ) : isReportParsing(rx.status) ? (
                      <p style={{ marginTop: 'var(--space-4)', fontSize: 'var(--font-sm)', color: 'var(--text-muted)' }}>
                        Reading this prescription in the background. This can take a minute for a photo or a scan.
                      </p>
                    ) : (
                      <>
                        <p style={{ marginTop: 'var(--space-4)', fontSize: 'var(--font-sm)', color: 'var(--text-muted)' }}>
                          No medicines were read from this prescription. Use “Read again” after setting up the OCR
                          model, or add them by hand.
                        </p>
                        <MedicationList
                          prescriptionId={rx.id}
                          medications={[]}
                          onChanged={() => fetchPrescriptions(true)}
                        />
                      </>
                    )}
                  </div>

                  {chatId === rx.id && (
                    <div className="report-compare-chat">
                      <AIChatPanel
                        subject="prescription"
                        id={rx.id}
                        hasRows={(rx.medications?.length ?? 0) > 0}
                        onClose={() => setChatId(null)}
                      />
                    </div>
                  )}

                  {originalId === rx.id && (
                    <div className="card report-compare-pdf">
                      {originalError ? (
                        <div className="alert alert-error">{originalError}</div>
                      ) : originalUrl ? (
                        originalType.startsWith('image/') ? (
                          <img
                            className="report-pdf-frame prescription-original-image"
                            src={originalUrl}
                            alt="Original prescription"
                          />
                        ) : (
                          <iframe
                            className="report-pdf-frame"
                            src={originalUrl}
                            title="Original prescription"
                          />
                        )
                      ) : (
                        <div className="skeleton report-pdf-frame" />
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showUpload && <UploadPrescriptionModal onClose={() => setShowUpload(false)} onSuccess={() => { setShowUpload(false); fetchPrescriptions(); }} />}
    </div>
  );
};

/* ---------- Upload Prescription Modal ---------- */
const UploadPrescriptionModal: React.FC<{ onClose: () => void; onSuccess: () => void }> = ({ onClose, onSuccess }) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [form, setForm] = useState({
    doctor_name: '',
    hospital_clinic: '',
    notes: '',
  });
  // Typed or pasted as text, and normalized on blur; parsed once, on submit.
  const [dateText, setDateText] = useState(todayIsoDate());
  const [dateError, setDateError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setDateError('');
    if (!file) { setError('Choose a prescription file first.'); return; }

    const prescriptionDate = parseDateInput(dateText);
    if (!prescriptionDate) {
      setDateError('Use a date like 2026-05-14, 14/05/2026, or 14 May 2026');
      return;
    }

    setUploading(true);
    try {
      await apiService.uploadPrescription(
        file, form.doctor_name, form.hospital_clinic, prescriptionDate, form.notes,
      );
      onSuccess();
    } catch (err) {
      // The server says which field it refused and why; a bare "Upload failed" hid that.
      setError(apiErrorMessage(err, 'Upload failed. Please try again.'));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Add Prescription</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <IconClose size={18} />
          </button>
        </div>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit} className="modal-body">
          <div className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}>
            <input ref={fileRef} type="file" accept={PRESCRIPTION_FILE_ACCEPT} hidden
              onChange={e => e.target.files?.[0] && setFile(e.target.files[0])} />
            {file ? (
              <><div className="upload-zone-text">{file.name}</div></>
            ) : (
              <>
                <div className="upload-zone-text">Drop the prescription here</div>
                <div className="upload-zone-hint">A PDF, or a photo of the paper</div>
              </>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
            <div className="form-group">
              <label className="form-label">Doctor Name</label>
              <input className="form-input" placeholder="Dr. Smith"
                value={form.doctor_name} onChange={e => setForm({ ...form, doctor_name: e.target.value })} />
            </div>
            <DateTextInput
              id="prescription-date"
              label="Date"
              value={dateText}
              onChange={value => { setDateText(value); setDateError(''); }}
              error={dateError}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Hospital / Clinic</label>
            <input className="form-input" placeholder="Hospital or clinic name"
              value={form.hospital_clinic} onChange={e => setForm({ ...form, hospital_clinic: e.target.value })} />
          </div>

          <div className="form-group">
            <label className="form-label">Notes</label>
            <textarea className="form-textarea" placeholder="Any additional notes…" style={{ minHeight: 60 }}
              value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          </div>

          <p className="form-hint">
            The medicines are read in the background once this is uploaded — a photo or a scan is read by the
            OCR model set up in AI settings.
          </p>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={uploading}>
              {uploading ? <><span className="spinner" /> Uploading…</> : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Prescriptions;
