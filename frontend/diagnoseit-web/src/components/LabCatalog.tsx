import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiService } from '../services/api';
import type { LabTestType, LabTestTypeInput, LabTestUnit } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';
import { IconSearch } from './Icons';

/**
 * The lab test catalog: the tests every report's results are matched against.
 *
 * The catalog is shared by everyone on the server, and every signed-in user can maintain it.
 * A test's other names decide which printed names join its trend, so every change re-matches stored results
 * and the page reports how many moved. Removing a test never deletes results: they go back to their printed
 * name. A built-in test is deactivated rather than deleted, because the catalog loader restores it on the
 * next deploy; it can be put back from the Removed tab.
 */

type Tab = 'active' | 'removed';

interface FormState {
  name: string;
  display_name: string;
  category: string;
  description: string;
  aliases: string;
  default_unit: string;
  normal_min: string;
  normal_max: string;
}

const EMPTY_FORM: FormState = {
  name: '',
  display_name: '',
  category: '',
  description: '',
  aliases: '',
  default_unit: '',
  normal_min: '',
  normal_max: '',
};

function formFor(entry: LabTestType): FormState {
  return {
    name: entry.name,
    display_name: entry.display_name,
    category: entry.category || '',
    description: entry.description || '',
    aliases: (entry.aliases || []).join(', '),
    default_unit: entry.default_unit || '',
    normal_min: entry.normal_min ?? '',
    normal_max: entry.normal_max ?? '',
  };
}

/** A decimal the API stores with trailing zeros ("70.0000") reads better as the number someone typed. */
function tidyNumber(value: string | null | undefined): string {
  if (value == null || value === '') return '';
  const n = Number(value);
  return Number.isFinite(n) ? String(n) : value;
}

const LabCatalog: React.FC = () => {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>('active');
  const [entries, setEntries] = useState<LabTestType[]>([]);
  const [units, setUnits] = useState<LabTestUnit[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [editing, setEditing] = useState<LabTestType | 'new' | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState<LabTestType | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async (which: Tab) => {
    setLoading(true);
    try {
      setEntries(await apiService.getAllLabTestTypes(undefined, which === 'removed' ? 'false' : 'true'));
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not load the test catalog'), 'error');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load(tab);
  }, [load, tab]);

  useEffect(() => {
    apiService
      .getAllLabTestUnits()
      .then(setUnits)
      .catch(() => { /* the form still works; the unit is typed instead of picked */ });
  }, []);

  const categories = useMemo(
    () => [...new Set(entries.map(entry => entry.category).filter(Boolean))].sort(),
    [entries],
  );

  const shown = useMemo(() => {
    const term = search.trim().toLowerCase();
    return entries.filter(entry => {
      if (category && entry.category !== category) return false;
      if (!term) return true;
      return (
        entry.display_name.toLowerCase().includes(term) ||
        entry.name.toLowerCase().includes(term) ||
        (entry.aliases || []).some(alias => alias.toLowerCase().includes(term))
      );
    });
  }, [entries, search, category]);

  const unitLabel = useCallback(
    (name?: string) => {
      const unit = units.find(item => item.name === name);
      return unit ? unit.symbol || unit.display_name : name || '—';
    },
    [units],
  );

  const openNew = () => {
    setEditing('new');
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const openEdit = (entry: LabTestType) => {
    setEditing(entry);
    setForm({ ...formFor(entry), normal_min: tidyNumber(entry.normal_min), normal_max: tidyNumber(entry.normal_max) });
    setFormError(null);
  };

  /** A new entry gets a key from its name, unless someone typed one. */
  const fillKey = async () => {
    if (editing !== 'new' || form.name.trim() || !form.display_name.trim()) return;
    try {
      const { key } = await apiService.suggestLabTestKey(form.display_name.trim());
      setForm(current => (current.name.trim() ? current : { ...current, name: key }));
    } catch {
      /* the key can be typed by hand */
    }
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    const payload: LabTestTypeInput = {
      display_name: form.display_name.trim(),
      category: form.category.trim(),
      description: form.description.trim(),
      aliases: form.aliases.split(',').map(alias => alias.trim()).filter(Boolean),
      default_unit: form.default_unit,
      normal_min: form.normal_min.trim() || null,
      normal_max: form.normal_max.trim() || null,
    };
    try {
      if (editing === 'new') {
        const created = await apiService.createLabTestType({ ...payload, name: form.name.trim() });
        toast(
          created.relinked
            ? `Added ${created.display_name}; ${created.relinked} stored result${created.relinked === 1 ? '' : 's'} now use it.`
            : `Added ${created.display_name}.`,
          'success',
        );
      } else if (editing) {
        const saved = await apiService.updateLabTestType(editing.name, payload);
        toast(
          saved.relinked
            ? `Saved ${saved.display_name}; ${saved.relinked} stored result${saved.relinked === 1 ? '' : 's'} moved.`
            : `Saved ${saved.display_name}.`,
          'success',
        );
      }
      setEditing(null);
      await load(tab);
    } catch (err) {
      setFormError(apiErrorMessage(err, 'Could not save this entry'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!removing) return;
    setBusy(removing.name);
    try {
      const { removed, unlinked } = await apiService.deleteLabTestType(removing.name);
      toast(
        `${removing.display_name} ${removed === 'deleted' ? 'deleted' : 'removed from the catalog'}` +
          (unlinked ? `; ${unlinked} result${unlinked === 1 ? '' : 's'} went back to the printed name.` : '.'),
        'success',
      );
      setRemoving(null);
      await load(tab);
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not remove this entry'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const restore = async (entry: LabTestType) => {
    setBusy(entry.name);
    try {
      const saved = await apiService.updateLabTestType(entry.name, { is_active: true, display_name: entry.display_name });
      toast(
        saved.relinked
          ? `${entry.display_name} is back; ${saved.relinked} result${saved.relinked === 1 ? '' : 's'} link to it again.`
          : `${entry.display_name} is back in the catalog.`,
        'success',
      );
      await load(tab);
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not put this entry back'), 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Test Catalog</h1>
          <p className="page-subtitle">
            The tests your report results are matched against. Changing a test's other names changes which
            printed names join its <Link to="/health-trends">trend</Link>.
          </p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={openNew}>Add test</button>
      </div>

      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'center' }}>
          <div className="search-bar" style={{ flex: '1 1 260px' }}>
            <span className="search-bar-icon" aria-hidden><IconSearch size={16} /></span>
            <input
              aria-label="Search the test catalog"
              className="form-input"
              placeholder="Search by name, key, or another name…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <select
            aria-label="Filter by category"
            className="form-select form-select-sm"
            value={category}
            onChange={e => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map(item => <option key={item} value={item}>{item}</option>)}
          </select>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button
              className={`btn btn-sm ${tab === 'active' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab('active')}
            >
              In use
            </button>
            <button
              className={`btn btn-sm ${tab === 'removed' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab('removed')}
            >
              Removed
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="stack">
          <div className="skeleton" style={{ height: 44 }} />
          <div className="skeleton" style={{ height: 240 }} />
        </div>
      ) : shown.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-state-title">
            {tab === 'removed' ? 'Nothing removed' : 'No tests match'}
          </div>
          <div className="empty-state-text">
            {tab === 'removed'
              ? 'Tests you remove from the catalog are listed here, so you can put one back.'
              : 'Try another search, or add the test the catalog is missing.'}
          </div>
        </div>
      ) : (
        <div className="card">
          <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
            {shown.length} test{shown.length !== 1 ? 's' : ''}
            {tab === 'active' && ' · a test edited here keeps its changes when the built-in catalog is reloaded on deploy'}
          </p>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Category</th>
                  <th>Unit</th>
                  <th>Normal range</th>
                  <th>Other names</th>
                  <th>Results</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {shown.map(entry => (
                  <tr key={entry.id}>
                    <td>
                      <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{entry.display_name}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-xs)', color: 'var(--text-muted)' }}>
                        {entry.name}
                      </div>
                      <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 4, flexWrap: 'wrap' }}>
                        {entry.source === 'user' && <span className="badge badge-info">added here</span>}
                        {entry.source !== 'user' && entry.edited_by_user && (
                          <span className="badge badge-purple" title="The catalog loader no longer overwrites this entry">
                            edited here
                          </span>
                        )}
                      </div>
                    </td>
                    <td>{entry.category || '—'}</td>
                    <td className="font-mono">{unitLabel(entry.default_unit)}</td>
                    <td className="font-mono">
                      {entry.normal_min != null || entry.normal_max != null
                        ? `${tidyNumber(entry.normal_min) || '—'} – ${tidyNumber(entry.normal_max) || '—'}`
                        : '—'}
                    </td>
                    <td style={{ maxWidth: 260, fontSize: 'var(--font-xs)', color: 'var(--text-muted)' }}>
                      {(entry.aliases || []).join(', ') || '—'}
                    </td>
                    <td className="font-mono">{entry.result_count ?? 0}</td>
                    <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
                      <button className="btn btn-secondary btn-sm" onClick={() => openEdit(entry)}>Edit</button>{' '}
                      {tab === 'removed' ? (
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={busy === entry.name}
                          onClick={() => restore(entry)}
                        >
                          Put back
                        </button>
                      ) : (
                        <button
                          className="btn btn-danger btn-sm"
                          disabled={busy === entry.name}
                          onClick={() => setRemoving(entry)}
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {editing && (
        <div className="modal-overlay" onClick={() => !saving && setEditing(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{editing === 'new' ? 'Add a test' : editing.display_name}</h2>
              <button className="modal-close" onClick={() => setEditing(null)} aria-label="Close">✕</button>
            </div>
            <form onSubmit={save}>
              <div className="modal-body">
                {formError && <div className="alert alert-error">{formError}</div>}

                <div className="form-group">
                  <label className="form-label" htmlFor="catalog-display-name">Name</label>
                  <input
                    id="catalog-display-name"
                    className="form-input"
                    required
                    value={form.display_name}
                    onChange={e => setForm({ ...form, display_name: e.target.value })}
                    onBlur={fillKey}
                    placeholder="Vitamin D (25-OH)"
                  />
                  <span className="form-hint">Shown on reports, trends, and the catalog.</span>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="catalog-key">Key</label>
                  <input
                    id="catalog-key"
                    className="form-input font-mono"
                    value={form.name}
                    disabled={editing !== 'new'}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="vitamin_d"
                  />
                  <span className="form-hint">
                    {editing === 'new'
                      ? 'Lowercase letters, numbers, and underscores. Left blank, it is made from the name.'
                      : 'The key never changes: stored results and name links refer to it.'}
                  </span>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="catalog-category">Category</label>
                  <input
                    id="catalog-category"
                    className="form-input"
                    value={form.category}
                    onChange={e => setForm({ ...form, category: e.target.value })}
                    list="catalog-categories"
                    placeholder="Chemistry"
                  />
                  <datalist id="catalog-categories">
                    {categories.map(item => <option key={item} value={item} />)}
                  </datalist>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="catalog-aliases">Other names</label>
                  <textarea
                    id="catalog-aliases"
                    className="form-textarea"
                    value={form.aliases}
                    onChange={e => setForm({ ...form, aliases: e.target.value })}
                    placeholder="25-hydroxyvitamin d, vit d total"
                  />
                  <span className="form-hint">
                    Separated by commas. A printed name matching one of these joins this test's trend, so a name
                    that already belongs to another test is refused.
                  </span>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="catalog-unit">Unit</label>
                  <select
                    id="catalog-unit"
                    className="form-select"
                    required
                    value={form.default_unit}
                    onChange={e => setForm({ ...form, default_unit: e.target.value })}
                  >
                    <option value="">Choose a unit…</option>
                    {units.map(unit => (
                      <option key={unit.id} value={unit.name}>
                        {unit.symbol || unit.display_name} — {unit.display_name}
                      </option>
                    ))}
                  </select>
                  <span className="form-hint">
                    The unit its normal range is written in. Results printed in another unit are converted when
                    the catalog knows a conversion for this test.
                  </span>
                </div>

                <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="form-label" htmlFor="catalog-min">Normal range, low</label>
                    <input
                      id="catalog-min"
                      className="form-input font-mono"
                      inputMode="decimal"
                      value={form.normal_min}
                      onChange={e => setForm({ ...form, normal_min: e.target.value })}
                      placeholder="optional"
                    />
                  </div>
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="form-label" htmlFor="catalog-max">Normal range, high</label>
                    <input
                      id="catalog-max"
                      className="form-input font-mono"
                      inputMode="decimal"
                      value={form.normal_max}
                      onChange={e => setForm({ ...form, normal_max: e.target.value })}
                      placeholder="optional"
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="catalog-description">Notes</label>
                  <input
                    id="catalog-description"
                    className="form-input"
                    value={form.description}
                    onChange={e => setForm({ ...form, description: e.target.value })}
                    placeholder="optional"
                  />
                </div>

                {editing !== 'new' && editing.source !== 'user' && (
                  <div className="alert alert-info">
                    Saving marks this built-in test as edited here, so the catalog loader stops overwriting it
                    on the next deploy.
                  </div>
                )}
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setEditing(null)} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving…' : editing === 'new' ? 'Add test' : 'Save changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {removing && (
        <div className="modal-overlay" onClick={() => setRemoving(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Remove {removing.display_name}?</h2>
              <button className="modal-close" onClick={() => setRemoving(null)} aria-label="Close">✕</button>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)' }}>
                {removing.result_count
                  ? `${removing.result_count} stored result${removing.result_count === 1 ? '' : 's'} link to this test. ` +
                    'They are kept and go back to the name printed on the report, so they leave this test’s trend.'
                  : 'No stored result links to this test yet.'}
              </p>
              <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)' }}>
                {removing.source === 'user'
                  ? 'This test was added here, so it is deleted for good.'
                  : 'This is a built-in test, so it moves to the Removed tab and can be put back. It stays removed when the catalog is reloaded on deploy.'}
              </p>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setRemoving(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={remove} disabled={busy === removing.name}>
                {busy === removing.name ? 'Removing…' : 'Remove'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LabCatalog;
