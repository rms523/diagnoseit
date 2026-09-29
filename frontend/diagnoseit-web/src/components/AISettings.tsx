import React, { useCallback, useEffect, useState } from 'react';
import { apiService } from '../services/api';
import type { AIConnectionCheck, AIRole, AIServiceSettings, AIServiceSettingsUpdate } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';

const ROLE_HELP: Record<AIRole, string> = {
  diagnosis:
    'Generates AI diagnoses. Works with any OpenAI-compatible chat server: OpenAI, llama.cpp, vLLM, LM Studio, or Ollama at /v1.',
  ocr: 'Reads scanned or image-only report pages while parsing. Choose a vision model.',
  report_review:
    'Checks parsed results against the original report, from the report page or automatically after parsing. Page images need a vision model.',
};

const SOURCE_LABELS: Record<AIServiceSettings['source'], string> = {
  database: 'Saved here',
  environment: 'Server environment defaults',
  diagnosis: 'Using AI diagnosis settings',
};

const AISettings: React.FC = () => {
  const { user } = useAuth();
  // The server accepts changes only from administrators, who decide where everyone's reports are sent.
  const canEdit = Boolean(user?.is_staff);
  const [services, setServices] = useState<AIServiceSettings[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      setServices(await apiService.getAISettings());
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not load AI settings'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="stack animate-fade-in">
      <div className="page-header">
        <div>
          <p className="eyebrow">Shared by all users</p>
          <h1 className="page-title">AI settings</h1>
          <p className="page-subtitle">
            Choose the servers and models for AI diagnosis, report OCR, and report review. Changes apply to every user from the next request.
          </p>
        </div>
      </div>

      <div className="info-banner">
        <div className="info-banner-content">
          Report contents and health data are sent to these servers. Prefer servers you run yourself for patient data.
        </div>
      </div>

      {!canEdit && (
        <div className="alert alert-info">Only administrators can change these settings.</div>
      )}

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <>
          <div className="skeleton" style={{ height: 280 }} />
          <div className="skeleton" style={{ height: 280 }} />
        </>
      ) : (
        services.map(service => (
          // Remount after save or reset so the form starts from the server's current values.
          <AIServiceCard
            key={`${service.role}-${service.source}-${service.updated_at ?? ''}`}
            service={service}
            canEdit={canEdit}
            onChanged={refresh}
          />
        ))
      )}
    </div>
  );
};

interface AIServiceCardProps {
  service: AIServiceSettings;
  canEdit: boolean;
  onChanged: () => Promise<void>;
}

const AIServiceCard: React.FC<AIServiceCardProps> = ({ service, canEdit, onChanged }) => {
  const { toast, confirm } = useToast();
  const role = service.role;
  const id = (field: string) => `ai-${role}-${field}`;
  const [form, setForm] = useState({
    enabled: service.enabled,
    provider: service.provider,
    base_url: service.base_url,
    model: service.model,
    timeout_seconds: String(service.timeout_seconds),
    max_tokens: String(service.max_tokens),
    temperature: service.temperature == null ? '' : String(service.temperature),
    parallel_requests: String(service.parallel_requests ?? 1),
    ocr_mode: service.ocr_mode,
    review_input: service.review_input,
    auto_review: service.auto_review,
    auto_apply: service.auto_apply,
  });
  const [apiKey, setApiKey] = useState('');
  const [clearApiKey, setClearApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [check, setCheck] = useState<AIConnectionCheck | null>(null);

  const update = <K extends keyof typeof form>(field: K, value: (typeof form)[K]) =>
    setForm(prev => ({ ...prev, [field]: value }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const data: AIServiceSettingsUpdate = {
      enabled: form.enabled,
      provider: form.provider,
      base_url: form.base_url.trim(),
      model: form.model.trim(),
      timeout_seconds: Number(form.timeout_seconds),
      max_tokens: Number(form.max_tokens),
      temperature: form.temperature.trim() === '' ? null : Number(form.temperature),
    };
    if (role === 'ocr') {
      data.ocr_mode = form.ocr_mode;
      data.parallel_requests = Number(form.parallel_requests) || 1;
    }
    if (role === 'report_review') {
      data.review_input = form.review_input;
      data.auto_review = form.auto_review;
      data.auto_apply = form.auto_apply;
    }
    if (apiKey) data.api_key = apiKey;
    else if (clearApiKey) data.clear_api_key = true;

    setSaving(true);
    try {
      await apiService.updateAISettings(role, data);
      toast(`${service.label} settings saved`, 'success');
      await onChanged();
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not save settings'), 'error');
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setCheck(null);
    try {
      setCheck(
        await apiService.testAISettings(role, {
          provider: form.provider,
          base_url: form.base_url.trim(),
          model: form.model.trim(),
          ...(apiKey ? { api_key: apiKey } : {}),
        })
      );
    } catch (err) {
      setCheck({ ok: false, models: [], error: apiErrorMessage(err, 'Connection check failed') });
    } finally {
      setTesting(false);
    }
  };

  const reset = async () => {
    const ok = await confirm(`Reset ${service.label} to the server's environment defaults?`);
    if (!ok) return;
    try {
      await apiService.resetAISettings(role);
      toast(`${service.label} reset to defaults`, 'success');
      await onChanged();
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not reset settings'), 'error');
    }
  };

  const baseUrlPlaceholder =
    role === 'ocr' && form.provider === 'ollama' ? 'http://localhost:11434' : 'http://localhost:8080/v1';

  return (
    <form className="card stack" onSubmit={save}>
      {/* display: contents keeps the card's layout; disabled still turns off every field inside. */}
      <fieldset disabled={!canEdit} style={{ display: 'contents' }}>
        <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'flex-start' }}>
          <div style={{ maxWidth: 640 }}>
            <h2 style={{ fontSize: 'var(--font-lg)' }}>{service.label}</h2>
            <p className="form-hint" style={{ marginTop: 'var(--space-1)' }}>{ROLE_HELP[role]}</p>
          </div>
          <div className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <span className="badge badge-muted">{SOURCE_LABELS[service.source]}</span>
            <span className={`badge ${service.is_configured ? 'badge-success' : 'badge-warning'}`}>
              {service.is_configured ? 'Ready' : 'Not configured'}
            </span>
          </div>
        </div>

        <label className="row" style={{ gap: 'var(--space-2)', width: 'fit-content' }}>
          <input type="checkbox" checked={form.enabled} onChange={e => update('enabled', e.target.checked)} />
          Enabled
        </label>

        {role === 'report_review' && (
          <>
            <label className="row" style={{ gap: 'var(--space-2)', width: 'fit-content', alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                checked={form.auto_review}
                onChange={e => update('auto_review', e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                Review every report automatically after it is parsed
                <span className="form-hint" style={{ display: 'block' }}>
                  Suggestions wait on the report page. Each report costs a model call, long reports several, and a bulk
                  upload one or more per file.
                </span>
              </span>
            </label>
            <label className="row" style={{ gap: 'var(--space-2)', width: 'fit-content', alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                checked={form.auto_apply}
                onChange={e => update('auto_apply', e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                Apply safe fixes automatically
                <span className="form-hint" style={{ display: 'block' }}>
                  Removes rows that are not results and corrects units, reference ranges, and status, only for rows the
                  model was shown in the report. Adding results, renaming tests, and changing values always wait for the
                  user. Every applied fix can be undone from the report page.
                </span>
              </span>
            </label>
          </>
        )}

        <div className="grid-2">
          {role === 'ocr' && (
            <div className="form-group">
              <label className="form-label" htmlFor={id('provider')}>API type</label>
              <select
                id={id('provider')}
                className="form-select"
                value={form.provider}
                onChange={e => update('provider', e.target.value as AIServiceSettings['provider'])}
              >
                <option value="openai">OpenAI-compatible (/v1/chat/completions)</option>
                <option value="ollama">Ollama native (/api/generate)</option>
              </select>
            </div>
          )}

          <div className="form-group">
            <label className="form-label" htmlFor={id('base-url')}>Server URL</label>
            <input
              id={id('base-url')}
              className="form-input"
              placeholder={baseUrlPlaceholder}
              value={form.base_url}
              onChange={e => update('base_url', e.target.value)}
            />
            {role !== 'ocr' && <div className="form-hint">Leave blank to use OpenAI's API with an API key.</div>}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor={id('model')}>Model</label>
            <input
              id={id('model')}
              className="form-input"
              list={id('models')}
              placeholder="Test the connection to list models"
              value={form.model}
              onChange={e => update('model', e.target.value)}
            />
            <datalist id={id('models')}>
              {(check?.models ?? []).map(name => <option key={name} value={name} />)}
            </datalist>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor={id('api-key')}>API key</label>
            <input
              id={id('api-key')}
              className="form-input"
              type="password"
              autoComplete="new-password"
              placeholder={service.api_key_set ? 'Key set; leave blank to keep it' : 'Optional for local servers'}
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
            />
            {service.source === 'database' && service.api_key_set && !apiKey
              && form.base_url.trim() !== service.base_url && (
              <div className="form-hint">Changing the server removes the saved key. Enter the key again if the new server needs one.</div>
            )}
            {service.source === 'database' && service.api_key_set && (
              <label className="row form-hint" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
                <input type="checkbox" checked={clearApiKey} onChange={e => setClearApiKey(e.target.checked)} />
                Remove the saved key
              </label>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor={id('timeout')}>Timeout (seconds)</label>
            <input
              id={id('timeout')}
              className="form-input"
              type="number"
              min={5}
              max={1800}
              value={form.timeout_seconds}
              onChange={e => update('timeout_seconds', e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor={id('max-tokens')}>Max tokens</label>
            <input
              id={id('max-tokens')}
              className="form-input"
              type="number"
              min={64}
              max={32000}
              value={form.max_tokens}
              onChange={e => update('max_tokens', e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor={id('temperature')}>Temperature</label>
            <input
              id={id('temperature')}
              className="form-input"
              type="number"
              min={0}
              max={2}
              step={0.05}
              placeholder={`Default (${service.default_temperature})`}
              value={form.temperature}
              onChange={e => update('temperature', e.target.value)}
            />
            <span className="form-hint">Lower gives more consistent answers. Leave blank for the default.</span>
          </div>

          {role === 'ocr' && (
            <div className="form-group">
              <label className="form-label" htmlFor={id('ocr-mode')}>OCR mode</label>
              <select
                id={id('ocr-mode')}
                className="form-select"
                value={form.ocr_mode}
                onChange={e => update('ocr_mode', e.target.value as AIServiceSettings['ocr_mode'])}
              >
                <option value="auto">Auto-detect from model name</option>
                <option value="paddle_ocr">PaddleOCR-VL (table and OCR prompts)</option>
                <option value="json_vlm">Vision model returning JSON</option>
              </select>
            </div>
          )}

          {role === 'ocr' && (
            <div className="form-group">
              <label className="form-label" htmlFor={id('parallel-requests')}>Pages at once</label>
              <input
                id={id('parallel-requests')}
                className="form-input"
                type="number"
                min={1}
                max={16}
                value={form.parallel_requests}
                onChange={e => update('parallel_requests', e.target.value)}
              />
              <span className="form-hint">
                Pages sent to the OCR server together. Match its parallel slots (llama-server -np); more pages use more memory.
              </span>
            </div>
          )}

          {role === 'report_review' && (
            <div className="form-group">
              <label className="form-label" htmlFor={id('review-input')}>Send to the model</label>
              <select
                id={id('review-input')}
                className="form-select"
                value={form.review_input}
                onChange={e => update('review_input', e.target.value as AIServiceSettings['review_input'])}
              >
                <option value="auto">PDF text, or page images for scans</option>
                <option value="text">PDF text only</option>
                <option value="images">Page images (vision model)</option>
              </select>
            </div>
          )}
        </div>

        {check && (
          <div className={`alert ${check.ok ? (check.warning ? 'alert-info' : 'alert-success') : 'alert-error'}`}>
            {check.ok
              ? `Connected in ${check.latency_ms} ms. ${check.models.length} model${check.models.length === 1 ? '' : 's'} available.${check.warning ? ` ${check.warning}` : ''}`
              : check.error}
            {check.ok && check.models.length > 0 && (
              <div className="row" style={{ flexWrap: 'wrap', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
                {check.models.map(name => (
                  <button
                    key={name}
                    type="button"
                    className={`btn btn-sm ${name === form.model ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => update('model', name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)' }}>
          <span className="form-hint">
            {service.updated_by &&
              `Last saved by ${service.updated_by}${service.updated_at ? ` on ${new Date(service.updated_at).toLocaleString()}` : ''}`}
          </span>
          {canEdit && (
            <div className="row" style={{ gap: 'var(--space-2)' }}>
              {service.source === 'database' && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={reset}>Reset to defaults</button>
              )}
              <button type="button" className="btn btn-secondary btn-sm" onClick={testConnection} disabled={testing}>
                {testing ? <><span className="spinner" /> Testing…</> : 'Test connection'}
              </button>
              <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          )}
        </div>
      </fieldset>
    </form>
  );
};

export default AISettings;
