import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import type { Symptom, SymptomLog } from '../services/api';
import { IconSymptoms, IconClose, IconCheck, IconRefresh, IconTrash, IconEdit } from './Icons';
import { apiErrorMessage } from '../utils/apiErrors';
import { dateTimeTextToIso, toDateTimeText } from '../utils/dates';
import DateTimeTextInput from './DateTimeTextInput';

const SEVERITY_MAP: Record<number, { label: string; color: string; badge: string }> = {
  1: { label: 'Mild', color: 'var(--accent-success)', badge: 'badge-success' },
  2: { label: 'Moderate', color: 'var(--accent-warning)', badge: 'badge-warning' },
  3: { label: 'Severe', color: '#D97706', badge: 'badge-danger' },
  4: { label: 'Very Severe', color: 'var(--accent-danger)', badge: 'badge-danger' },
};

const DURATION_MAP: Record<string, string> = {
  ACUTE: 'Acute (< 1 week)',
  SUBACUTE: 'Subacute (1–4 weeks)',
  CHRONIC: 'Chronic (> 4 weeks)',
};

const Symptoms: React.FC = () => {
  const { toast, confirm } = useToast();
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingSymptom, setEditingSymptom] = useState<Symptom | null>(null);
  const [logsFor, setLogsFor] = useState<number | null>(null);
  const [symptomLogs, setSymptomLogs] = useState<SymptomLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'active' | 'resolved'>('all');
  const [error, setError] = useState('');

  const fetchSymptoms = async () => {
    try {
      const data = await apiService.getSymptoms();
      setSymptoms(data);
    } catch { setError('Failed to load symptoms'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchSymptoms(); }, []);

  const handleDelete = async (id: number) => {
    const ok = await confirm('Delete this symptom?');
    if (!ok) return;
    try {
      await apiService.deleteSymptom(id);
      setSymptoms(prev => prev.filter(s => s.id !== id));
      toast('Symptom deleted', 'success');
    } catch { toast('Failed to delete', 'error'); }
  };

  const toggleResolved = async (symptom: Symptom) => {
    try {
      const updated = await apiService.updateSymptom(symptom.id, { is_ongoing: !symptom.is_ongoing });
      setSymptoms(prev => prev.map(s => s.id === updated.id ? updated : s));
      toast(updated.is_ongoing ? 'Symptom reopened' : 'Symptom resolved', 'success');
    } catch { toast('Failed to update', 'error'); }
  };

  const openLogs = async (symptomId: number) => {
    if (logsFor === symptomId) {
      setLogsFor(null);
      return;
    }
    setLogsFor(symptomId);
    setLogsLoading(true);
    try {
      const logs = await apiService.getSymptomLogs(symptomId);
      setSymptomLogs(logs);
    } catch {
      toast('Failed to load symptom logs', 'error');
      setSymptomLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  const addLog = async (symptomId: number, severity: number, notes: string) => {
    try {
      const entry = await apiService.createSymptomLog(symptomId, {
        severity,
        notes: notes.trim() || undefined,
      });
      setSymptomLogs(prev => [entry, ...prev]);
      toast('Log entry added', 'success');
    } catch {
      toast('Failed to add log entry', 'error');
    }
  };

  const filtered = symptoms.filter(s => {
    if (filter === 'active') return s.is_ongoing;
    if (filter === 'resolved') return !s.is_ongoing;
    return true;
  });

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
          <h1 className="page-title">Symptoms</h1>
          <p className="page-subtitle">Track and manage your symptoms</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>Log symptom</button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 'var(--space-4)' }}>{error}</div>}

      {/* Filter tabs */}
      <div className="row" style={{ marginBottom: 'var(--space-6)', gap: 'var(--space-2)' }}>
        {(['all', 'active', 'resolved'] as const).map(f => (
          <button key={f} className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setFilter(f)}>
            {f === 'all' ? `All (${symptoms.length})` :
             f === 'active' ? `Active (${symptoms.filter(s => s.is_ongoing).length})` :
             `Resolved (${symptoms.filter(s => !s.is_ongoing).length})`}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-state-icon"><IconSymptoms size={32} /></div>
          <div className="empty-state-title">{filter === 'all' ? 'No symptoms logged' : `No ${filter} symptoms`}</div>
          <div className="empty-state-text">Track your symptoms to get better health insights</div>
          {filter === 'all' && <button className="btn btn-primary" onClick={() => setShowAdd(true)}>Log Symptom</button>}
        </div>
      ) : (
        <div className="stack stagger-children">
          {filtered.map(symptom => {
            const sev = SEVERITY_MAP[symptom.severity] || SEVERITY_MAP[1];
            return (
              <div key={symptom.id} className="card">
                <div className="row-between">
                  <div style={{ flex: 1 }}>
                    <div className="row" style={{ marginBottom: 'var(--space-2)', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>
                        {symptom.description}
                      </span>
                      <span className={`badge ${sev.badge}`}>{sev.label}</span>
                      <span className={`badge ${symptom.is_ongoing ? 'badge-info' : 'badge-muted'}`}>
                        {symptom.is_ongoing ? '● Active' : '○ Resolved'}
                      </span>
                    </div>
                    <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
                      {symptom.body_part && <span>{symptom.body_part}</span>}
                      <span>{DURATION_MAP[symptom.duration] || symptom.duration}</span>
                      <span className="font-mono">{new Date(symptom.onset_date).toLocaleDateString()}</span>
                    </div>
                    {symptom.notes && (
                      <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginTop: 'var(--space-2)' }}>
                        {symptom.notes}
                      </p>
                    )}
                    {/* Severity dots */}
                    <div className="severity-dots" style={{ marginTop: 'var(--space-2)' }}>
                      {[1,2,3,4].map(i => {
                        const classes = ['severity-dot'];
                        if (i <= symptom.severity) {
                          classes.push('active');
                          if (symptom.severity === 1) classes.push('mild');
                          else if (symptom.severity === 2) classes.push('moderate');
                          else if (symptom.severity === 3) classes.push('severe');
                          else classes.push('very-severe');
                        }
                        return <div key={i} className={classes.join(' ')} />;
                      })}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 'var(--space-2)', flexShrink: 0, marginLeft: 'var(--space-3)', flexWrap: 'wrap' }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => setEditingSymptom(symptom)}>
                      <IconEdit size={14} /> Edit
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => openLogs(symptom.id)}>
                      Logs
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => toggleResolved(symptom)}>
                      {symptom.is_ongoing ? (
                        <><IconCheck size={14} /> Resolve</>
                      ) : (
                        <><IconRefresh size={14} /> Reopen</>
                      )}
                    </button>
                    <button className="btn btn-danger btn-sm" aria-label="Delete symptom" onClick={() => handleDelete(symptom.id)}>
                      <IconTrash size={14} />
                    </button>
                  </div>
                </div>
                {logsFor === symptom.id && (
                  <SymptomLogsPanel
                    logs={symptomLogs}
                    loading={logsLoading}
                    onAdd={(severity, notes) => addLog(symptom.id, severity, notes)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {showAdd && <AddSymptomModal onClose={() => setShowAdd(false)} onSuccess={() => { setShowAdd(false); fetchSymptoms(); }} />}
      {editingSymptom && (
        <EditSymptomModal
          symptom={editingSymptom}
          onClose={() => setEditingSymptom(null)}
          onSuccess={() => { setEditingSymptom(null); fetchSymptoms(); }}
        />
      )}
    </div>
  );
};

const SymptomLogsPanel: React.FC<{
  logs: SymptomLog[];
  loading: boolean;
  onAdd: (severity: number, notes: string) => void;
}> = ({ logs, loading, onAdd }) => {
  const [severity, setSeverity] = useState(2);
  const [notes, setNotes] = useState('');

  return (
    <div style={{ marginTop: 'var(--space-4)', paddingTop: 'var(--space-4)', borderTop: '1px solid var(--border-color)' }}>
      <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>Symptom Logs</div>
      <div className="row" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
        <div className="form-group" style={{ margin: 0, minWidth: 120 }}>
          <label className="form-label">Severity</label>
          <input type="number" min={1} max={4} className="form-input" value={severity}
            onChange={e => setSeverity(Math.min(4, Math.max(1, +e.target.value || 1)))} />
        </div>
        <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 200 }}>
          <label className="form-label">Notes</label>
          <input className="form-input" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional notes" />
        </div>
        <button type="button" className="btn btn-primary btn-sm" style={{ alignSelf: 'flex-end' }}
          onClick={() => { onAdd(severity, notes); setNotes(''); }}>
          Add log
        </button>
      </div>
      {loading ? (
        <div className="spinner" />
      ) : logs.length === 0 ? (
        <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-muted)' }}>No logs yet.</p>
      ) : (
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {logs.map(log => (
            <div key={log.id} style={{ fontSize: 'var(--font-sm)', padding: 'var(--space-2) var(--space-3)', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)' }}>
              <strong>Severity {log.severity}</strong>
              <span style={{ color: 'var(--text-muted)', marginLeft: 'var(--space-2)' }}>
                {new Date(log.logged_at).toLocaleString()}
              </span>
              {log.notes && <div style={{ marginTop: 'var(--space-1)', color: 'var(--text-secondary)' }}>{log.notes}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const EditSymptomModal: React.FC<{ symptom: Symptom; onClose: () => void; onSuccess: () => void }> = ({ symptom, onClose, onSuccess }) => {
  const [form, setForm] = useState({
    description: symptom.description,
    severity: symptom.severity,
    duration: symptom.duration,
    body_part: symptom.body_part || '',
    onset_date: toDateTimeText(new Date(symptom.onset_date)),
    notes: symptom.notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.description.trim()) { setError('Description is required'); return; }
    // The onset is typed or picked as text: a date with an optional time, in the viewer's time zone.
    const onsetDate = dateTimeTextToIso(form.onset_date);
    if (!onsetDate) { setError('Enter the onset as a date like 14/05/2026, optionally with a time like 09:30'); return; }
    setSaving(true);
    setError('');
    try {
      // Body part and notes are sent even when empty, so clearing them saves.
      await apiService.updateSymptom(symptom.id, {
        description: form.description,
        severity: form.severity,
        duration: form.duration,
        body_part: form.body_part,
        onset_date: onsetDate,
        notes: form.notes,
      });
      onSuccess();
    } catch (err) { setError(apiErrorMessage(err, 'Failed to update symptom')); }
    finally { setSaving(false); }
  };

  const sev = SEVERITY_MAP[form.severity];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Edit Symptom</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <IconClose size={18} />
          </button>
        </div>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="form-group">
            <label className="form-label">Description *</label>
            <textarea className="form-textarea" value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })} required />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
            <div className="form-group">
              <label className="form-label">Severity: <span style={{ color: sev.color, fontWeight: 600 }}>{sev.label}</span></label>
              <input type="range" min="1" max="4" value={form.severity}
                onChange={e => setForm({ ...form, severity: +e.target.value as 1|2|3|4 })}
                style={{ accentColor: sev.color, width: '100%' }} />
            </div>
            <div className="form-group">
              <label className="form-label">Duration</label>
              <select className="form-select" value={form.duration}
                onChange={e => setForm({ ...form, duration: e.target.value as 'ACUTE'|'SUBACUTE'|'CHRONIC' })}>
                <option value="ACUTE">Acute (&lt; 1 week)</option>
                <option value="SUBACUTE">Subacute (1–4 weeks)</option>
                <option value="CHRONIC">Chronic (&gt; 4 weeks)</option>
              </select>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
            <div className="form-group">
              <label className="form-label">Body Part</label>
              <input className="form-input" value={form.body_part}
                onChange={e => setForm({ ...form, body_part: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="symptom-onset">Onset Date</label>
              <DateTimeTextInput id="symptom-onset" value={form.onset_date}
                onChange={value => setForm({ ...form, onset_date: value })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Notes</label>
            <textarea className="form-textarea" style={{ minHeight: 70 }} value={form.notes}
              onChange={e => setForm({ ...form, notes: e.target.value })} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? <><span className="spinner" /> Saving…</> : <><IconCheck size={14} /> Save changes</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

/* ---------- Add Symptom Modal ---------- */
const AddSymptomModal: React.FC<{ onClose: () => void; onSuccess: () => void }> = ({ onClose, onSuccess }) => {
  const [form, setForm] = useState({
    description: '',
    severity: 1 as 1|2|3|4,
    duration: 'ACUTE' as 'ACUTE'|'SUBACUTE'|'CHRONIC',
    body_part: '',
    onset_date: toDateTimeText(new Date()),
    notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.description.trim()) { setError('Description is required'); return; }
    // The onset is typed or picked as text: a date with an optional time, in the viewer's time zone.
    const onsetDate = dateTimeTextToIso(form.onset_date);
    if (!onsetDate) { setError('Enter the onset as a date like 14/05/2026, optionally with a time like 09:30'); return; }
    setSaving(true);
    setError('');
    try {
      await apiService.createSymptom({
        description: form.description,
        severity: form.severity,
        duration: form.duration,
        body_part: form.body_part || undefined,
        onset_date: onsetDate,
        notes: form.notes || undefined,
      });
      onSuccess();
    } catch (err) { setError(apiErrorMessage(err, 'Failed to create symptom')); }
    finally { setSaving(false); }
  };

  const sev = SEVERITY_MAP[form.severity];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Log Symptom</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <IconClose size={18} />
          </button>
        </div>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="form-group">
            <label className="form-label">Description *</label>
            <textarea className="form-textarea" placeholder="Describe your symptom…"
              value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} required />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
            <div className="form-group">
              <label className="form-label">Severity: <span style={{ color: sev.color, fontWeight: 600 }}>{sev.label}</span></label>
              <input type="range" min="1" max="4" value={form.severity}
                onChange={e => setForm({ ...form, severity: +e.target.value as 1|2|3|4 })}
                style={{ accentColor: sev.color, width: '100%' }} />
            </div>
            <div className="form-group">
              <label className="form-label">Duration</label>
              <select className="form-select" value={form.duration}
                onChange={e => setForm({ ...form, duration: e.target.value as 'ACUTE'|'SUBACUTE'|'CHRONIC' })}>
                <option value="ACUTE">Acute (&lt; 1 week)</option>
                <option value="SUBACUTE">Subacute (1–4 weeks)</option>
                <option value="CHRONIC">Chronic (&gt; 4 weeks)</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
            <div className="form-group">
              <label className="form-label">Body Part</label>
              <input className="form-input" placeholder="e.g. head, chest, back"
                value={form.body_part} onChange={e => setForm({ ...form, body_part: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="symptom-onset">Onset Date</label>
              <DateTimeTextInput id="symptom-onset" value={form.onset_date}
                onChange={value => setForm({ ...form, onset_date: value })} />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Notes</label>
            <textarea className="form-textarea" placeholder="Any additional details…" style={{ minHeight: 70 }}
              value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? <><span className="spinner" /> Saving…</> : <><IconCheck size={14} /> Log symptom</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Symptoms;
