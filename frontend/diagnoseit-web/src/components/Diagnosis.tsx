import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import type { Diagnosis, DiagnosisContext, DiagnosisPeriod, DiagnosisTimelinePreview, Symptom } from '../services/api';
import { apiErrorMessage } from '../utils/apiErrors';
import DiagnosisAnalysis from './DiagnosisAnalysis';
import { IconDiagnosis, IconClose, IconCheck, IconInfo, IconTrash } from './Icons';

const PERIOD_OPTIONS: { value: DiagnosisPeriod; label: string }[] = [
  { value: '3m', label: 'Last 3 months' },
  { value: '6m', label: 'Last 6 months' },
  { value: '1y', label: 'Last year' },
  { value: '2y', label: 'Last 2 years' },
  { value: 'all', label: 'Everything' },
];

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;

/** "Health timeline since 15/9/2025 · 12 reports, 4 symptoms, 2 prescriptions" */
function timelineDescription(context: DiagnosisContext): string {
  const counts = context.counts ?? {};
  const parts = [
    counts.reports ? plural(counts.reports, 'report') : '',
    counts.symptoms ? plural(counts.symptoms, 'symptom') : '',
    counts.prescriptions ? plural(counts.prescriptions, 'prescription') : '',
    counts.assessments ? plural(counts.assessments, 'earlier assessment') : '',
  ].filter(Boolean);
  const since = context.since ? `since ${new Date(`${context.since}T00:00:00`).toLocaleDateString()}` : 'all records';
  return `Health timeline ${since}${parts.length ? ` · ${parts.join(', ')}` : ' · nothing recorded'}`;
}

const Diagnoses: React.FC = () => {
  const { toast, confirm } = useToast();
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [loading, setLoading] = useState(true);
  const [showGenerate, setShowGenerate] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [llmConfigured, setLlmConfigured] = useState(true);

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [dRes, sRes] = await Promise.allSettled([
          apiService.getDiagnoses(),
          apiService.getActiveSymptoms(),
        ]);
        if (dRes.status === 'fulfilled') {
          const results = dRes.value;
          setDiagnoses(results);
          // Detect if LLM is not configured from existing results
          if (results.some((d: Diagnosis) => d.condition_name === 'LLM Service Not Configured')) {
            setLlmConfigured(false);
          }
        }
        if (sRes.status === 'fulfilled') setSymptoms(sRes.value ?? []);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    };
    fetchAll();
  }, []);

  const refetch = async () => {
    try {
      const d = await apiService.getDiagnoses();
      const results = d;
      setDiagnoses(results);
      if (results.some((d: Diagnosis) => d.condition_name === 'LLM Service Not Configured')) {
        setLlmConfigured(false);
      }
    } catch { /* ignore */ }
  };

  const handleDelete = async (id: number) => {
    const ok = await confirm('Delete this diagnosis? This cannot be undone.');
    if (!ok) return;
    try {
      await apiService.deleteDiagnosis(id);
      setDiagnoses(prev => prev.filter(d => d.id !== id));
      toast('Diagnosis deleted', 'success');
    } catch {
      toast('Failed to delete diagnosis', 'error');
    }
  };

  const confidenceColor = (score: number) => {
    if (score >= 4) return 'var(--accent-success)';
    if (score >= 3) return 'var(--accent-primary)';
    if (score >= 2) return 'var(--accent-warning)';
    return 'var(--accent-danger)';
  };

  if (loading) {
    return (
      <div className="stack">
        <div className="skeleton" style={{ height: 48, width: 220 }} />
        <div className="skeleton" style={{ height: 120 }} />
        {[1,2].map(i => <div key={i} className="skeleton" style={{ height: 100 }} />)}
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Diagnosis</h1>
          <p className="page-subtitle">Generate AI-powered health insights from your data</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowGenerate(true)}>Generate diagnosis</button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 'var(--space-4)' }}>{error}</div>}

      {/* LLM not configured banner */}
      {!llmConfigured && (
        <div className="info-banner">
          <span className="info-banner-icon" aria-hidden>!</span>
          <div className="info-banner-content">
            <h4>AI Service Not Configured</h4>
            <p>
              The OpenAI API key is not set. Diagnosis generation will return placeholder results.
              To enable real AI analysis, set the <code style={{ color: 'var(--accent-primary)' }}>OPENAI_API_KEY</code> environment variable in your <code style={{ color: 'var(--accent-primary)' }}>.env</code> file.
            </p>
          </div>
        </div>
      )}

      {/* CTA Card */}
      <div className="card-gradient" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="row" style={{ gap: 'var(--space-4)', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <p className="eyebrow" style={{ marginBottom: 'var(--space-2)' }}>Analysis</p>
            <h3 style={{ fontSize: 'var(--font-lg)', marginBottom: 'var(--space-2)' }}>
              AI-powered review
            </h3>
            <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)' }}>
              Our AI analyzes your symptoms, test results, and medical history to provide personalized health insights and recommendations.
            </p>
          </div>
          <button className="btn btn-primary btn-lg" onClick={() => setShowGenerate(true)}>
            Generate now
          </button>
        </div>
      </div>

      {/* Diagnoses List */}
      {diagnoses.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-state-icon"><IconDiagnosis size={32} /></div>
          <div className="empty-state-title">No diagnoses yet</div>
          <div className="empty-state-text">Generate your first AI diagnosis to get health insights</div>
        </div>
      ) : (
        <div className="stack stagger-children">
          <h3 style={{ fontSize: 'var(--font-lg)', color: 'var(--text-secondary)' }}>History ({diagnoses.length})</h3>
          {diagnoses.map(d => (
            <div key={d.id} className="card" style={{ cursor: 'pointer' }}
              onClick={() => setExpandedId(expandedId === d.id ? null : d.id)}>
              <div className="row-between" style={{ marginBottom: 'var(--space-2)' }}>
                <div>
                  <div style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>{d.condition_name}</div>
                  <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                    {new Date(d.created_at).toLocaleDateString()} at {new Date(d.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                  {d.context?.mode === 'timeline' && (
                    <div className="font-mono" style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                      {timelineDescription(d.context)}
                    </div>
                  )}
                </div>
                <div className="row" style={{ gap: 'var(--space-2)' }}>
                  {d.follow_up_required && <span className="badge badge-warning">Follow-up needed</span>}
                  <span className="badge badge-purple">
                    Confidence: {d.confidence_score}/5
                  </span>
                  <button className="btn btn-danger btn-sm" aria-label="Delete diagnosis"
                    onClick={e => { e.stopPropagation(); handleDelete(d.id); }}>
                    <IconTrash size={14} />
                  </button>
                </div>
              </div>

              {/* Confidence bar */}
              <div className="confidence-bar" style={{ marginBottom: 'var(--space-3)' }}>
                <div className="confidence-fill" style={{
                  width: `${(d.confidence_score / 5) * 100}%`,
                  background: confidenceColor(d.confidence_score),
                }} />
              </div>

              {expandedId === d.id && (
                <div style={{ animation: 'slideUp 0.3s ease' }}>
                  {d.description && (
                    <div style={{ marginBottom: 'var(--space-4)' }}>
                      <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--accent-primary)', marginBottom: 'var(--space-2)' }}>Description</div>
                      <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{d.description}</p>
                    </div>
                  )}

                  {d.analysis && <DiagnosisAnalysis analysis={d.analysis} />}

                  {d.recommendations && (
                    <div style={{ marginTop: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
                      <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--accent-success)', marginBottom: 'var(--space-2)' }}>Recommendations</div>
                      <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{d.recommendations}</p>
                    </div>
                  )}

                  {d.follow_up_notes && (
                    <div>
                      <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--accent-warning)', marginBottom: 'var(--space-2)' }}>Follow-up Notes</div>
                      <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{d.follow_up_notes}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showGenerate && (
        <GenerateModal
          symptoms={symptoms}
          onClose={() => setShowGenerate(false)}
          onSuccess={() => { setShowGenerate(false); refetch(); }}
          onError={(msg) => setError(msg)}
        />
      )}
    </div>
  );
};

/* ---------- Generate Diagnosis Modal ---------- */
interface GenerateModalProps {
  symptoms: Symptom[];
  onClose: () => void;
  onSuccess: () => void;
  onError: (msg: string) => void;
}

const GenerateModal: React.FC<GenerateModalProps> = ({ symptoms: availableSymptoms, onClose, onSuccess, onError }) => {
  const [mode, setMode] = useState<'symptoms' | 'timeline'>('symptoms');
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [customSymptoms, setCustomSymptoms] = useState('');
  const [includeHistory, setIncludeHistory] = useState(true);
  const [includeTests, setIncludeTests] = useState(true);
  const [period, setPeriod] = useState<DiagnosisPeriod>('1y');
  const [summary, setSummary] = useState('');
  const [preview, setPreview] = useState<DiagnosisTimelinePreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [timelineError, setTimelineError] = useState('');
  const [generating, setGenerating] = useState(false);

  // The summary is saved to the profile with each timeline diagnosis, so it starts from the last one.
  useEffect(() => {
    apiService
      .getProfile()
      .then(user => setSummary(current => current || user.health_summary || ''))
      .catch(() => { /* start with an empty summary */ });
  }, []);

  const toggleSymptom = (desc: string) => {
    setPreview(null);
    setSelectedSymptoms(prev =>
      prev.includes(desc) ? prev.filter(s => s !== desc) : [...prev, desc]
    );
  };

  const currentSymptoms = () => [
    ...selectedSymptoms,
    ...customSymptoms.split(',').map(s => s.trim()).filter(Boolean),
  ];

  const showPreview = async () => {
    setPreviewing(true);
    setTimelineError('');
    try {
      setPreview(await apiService.previewDiagnosisTimeline({ period, summary, symptoms: currentSymptoms() }));
    } catch (err) {
      setTimelineError(apiErrorMessage(err, 'Could not build the timeline'));
    } finally {
      setPreviewing(false);
    }
  };

  const handleGenerate = async () => {
    const allSymptoms = currentSymptoms();
    if (mode === 'timeline') {
      setGenerating(true);
      setTimelineError('');
      try {
        await apiService.generateDiagnosis({ mode: 'timeline', period, summary, symptoms: allSymptoms });
        onSuccess();
      } catch (err) {
        setTimelineError(apiErrorMessage(err, 'Failed to generate diagnosis'));
      } finally {
        setGenerating(false);
      }
      return;
    }
    if (allSymptoms.length === 0) { onError('Please select or enter at least one symptom'); return; }

    setGenerating(true);
    try {
      await apiService.generateDiagnosis({
        symptoms: allSymptoms,
        include_medical_history: includeHistory,
        include_test_results: includeTests,
      });
      onSuccess();
    } catch {
      onError('Failed to generate diagnosis. Make sure the OpenAI API key is configured.');
    } finally {
      setGenerating(false);
    }
  };

  const timeline = mode === 'timeline';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: timeline ? 760 : 560 }}>
        <div className="modal-header">
          <h2 className="modal-title">Generate diagnosis</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <IconClose size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="row" role="group" aria-label="What to send" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
            <button
              type="button"
              className={`btn btn-sm ${!timeline ? 'btn-primary' : 'btn-secondary'}`}
              aria-pressed={!timeline}
              onClick={() => setMode('symptoms')}
            >
              Current symptoms
            </button>
            <button
              type="button"
              className={`btn btn-sm ${timeline ? 'btn-primary' : 'btn-secondary'}`}
              aria-pressed={timeline}
              onClick={() => setMode('timeline')}
            >
              Health timeline
            </button>
          </div>

          {timeline && (
            <>
              <div className="form-group">
                <label className="form-label" htmlFor="diagnosis-period">Period</label>
                <select
                  id="diagnosis-period"
                  className="form-select"
                  value={period}
                  onChange={e => { setPeriod(e.target.value as DiagnosisPeriod); setPreview(null); }}
                >
                  {PERIOD_OPTIONS.map(option => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="diagnosis-summary">Your summary for the AI</label>
                <textarea
                  id="diagnosis-summary"
                  className="form-textarea"
                  rows={4}
                  maxLength={4000}
                  placeholder="e.g. Type 2 diabetes since 2024, on metformin. I want to know whether my HbA1c and kidney results are improving."
                  value={summary}
                  onChange={e => { setSummary(e.target.value); setPreview(null); }}
                />
                <span className="form-hint">
                  Saved to your profile for next time. Your name, phone numbers, and emails are removed before sending.
                </span>
              </div>
            </>
          )}

          {/* Select from active symptoms */}
          {availableSymptoms.length > 0 && (
            <div className="form-group">
              <label className="form-label">{timeline ? 'Anything to ask about now (optional)' : 'Select active symptoms'}</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
                {availableSymptoms.map(s => (
                  <button key={s.id} type="button"
                    className={`btn btn-sm ${selectedSymptoms.includes(s.description) ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => toggleSymptom(s.description)}>
                    {selectedSymptoms.includes(s.description) && <IconCheck size={12} />}
                    {s.description.slice(0, 30)}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Additional symptoms (comma-separated)</label>
            <input className="form-input" placeholder="e.g. headache, fever, fatigue"
              value={customSymptoms} onChange={e => { setCustomSymptoms(e.target.value); setPreview(null); }} />
          </div>

          {!timeline && (
            <div style={{ display: 'flex', gap: 'var(--space-6)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                <input type="checkbox" checked={includeHistory} onChange={e => setIncludeHistory(e.target.checked)}
                  style={{ accentColor: 'var(--accent-primary)' }} />
                Include medical history
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                <input type="checkbox" checked={includeTests} onChange={e => setIncludeTests(e.target.checked)}
                  style={{ accentColor: 'var(--accent-primary)' }} />
                Include test results
              </label>
            </div>
          )}

          <div className="alert alert-info">
            <IconInfo size={16} />
            <span>
              {timeline
                ? 'Sends every lab result, symptom, prescription, and earlier AI assessment from this period, oldest first, so the AI can follow how your health changed. Long histories take longer, and the earliest dates are left out if the history is too long.'
                : 'The AI will analyze your selected symptoms along with your medical data to provide health insights.'}
            </span>
          </div>

          {timeline && timelineError && <div className="alert alert-error">{timelineError}</div>}

          {timeline && preview && (
            <div className="form-group">
              <p className="form-hint">
                {timelineDescription({ since: preview.since, counts: preview.counts })}
                {preview.omitted_dates > 0 && ` · the ${plural(preview.omitted_dates, 'earliest date')} left out`}
              </p>
              <pre
                style={{
                  maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 'var(--font-xs)',
                  background: 'var(--paper-muted)', padding: 'var(--space-3)', borderRadius: 8, margin: 0,
                }}
              >
                {preview.prompt}
              </pre>
            </div>
          )}

          <div className="modal-actions">
            <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
            {timeline && (
              <button className="btn btn-secondary" onClick={showPreview} disabled={previewing || generating}>
                {previewing ? <><span className="spinner" /> Building…</> : 'Preview what is sent'}
              </button>
            )}
            <button className="btn btn-primary btn-lg" onClick={handleGenerate} disabled={generating}>
              {generating ? <><span className="spinner" /> Analyzing…</> : 'Generate diagnosis'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Diagnoses;
