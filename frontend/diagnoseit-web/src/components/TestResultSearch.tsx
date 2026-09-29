import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiService } from '../services/api';
import type { TestResultSearchHit } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';
import { IconSearch, IconTrash } from './Icons';

interface TestResultSearchProps {
  /** Called after a result is deleted, so report result counts can refresh. */
  onResultDeleted: () => void;
  /** A heading and a line under it, for pages where the card needs to say what it is for. */
  heading?: string;
  hint?: string;
}

/**
 * Finds which reports contain a test, by printed or catalog name, and deletes results that are not tests.
 * The query is kept in the page URL (?test=NAME), so other pages can link here and it survives opening a report.
 */
const TestResultSearch: React.FC<TestResultSearchProps> = ({ onResultDeleted, heading, hint }) => {
  const { toast, confirm } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeQuery = (searchParams.get('test') ?? '').trim();
  const [query, setQuery] = useState(activeQuery);
  const [hits, setHits] = useState<TestResultSearchHit[] | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (activeQuery.length < 2) return;
    let cancelled = false;
    apiService
      .searchTestResults(activeQuery)
      .then(data => {
        if (cancelled) return;
        setHits(data.results);
        setTruncated(data.truncated);
        setError('');
      })
      .catch(err => {
        if (cancelled) return;
        setHits(null);
        setError(apiErrorMessage(err, 'Search failed'));
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeQuery, refreshKey]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setError('Type at least 2 characters.');
      return;
    }
    setSearching(true);
    if (trimmed === activeQuery) setRefreshKey(key => key + 1);
    else setTestParam(trimmed);
  };

  // Keep the page's other address settings (report search, sort, filter) while changing the test.
  const setTestParam = (value: string) =>
    setSearchParams(previous => {
      const next = new URLSearchParams(previous);
      if (value) next.set('test', value);
      else next.delete('test');
      return next;
    }, { replace: true });

  const clear = () => {
    setQuery('');
    setHits(null);
    setError('');
    setTestParam('');
  };

  const remove = async (hit: TestResultSearchHit) => {
    const ok = await confirm(`Delete “${hit.test_name}: ${hit.value}” from ${hit.report.title}?`);
    if (!ok) return;
    setDeletingId(hit.id);
    try {
      await apiService.deleteTestResult(hit.report.id, hit.id);
      setHits(previous => previous?.filter(item => item.id !== hit.id) ?? null);
      toast('Result deleted', 'success');
      onResultDeleted();
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not delete this result'), 'error');
    } finally {
      setDeletingId(null);
    }
  };

  const reportCount = new Set((hits ?? []).map(hit => hit.report.id)).size;

  return (
    <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
      {heading && (
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <h3 style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>{heading}</h3>
          {hint && <p className="form-hint" style={{ marginTop: 'var(--space-1)' }}>{hint}</p>}
        </div>
      )}
      <form onSubmit={submit} className="row" style={{ gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        <div className="search-bar" style={{ flex: '1 1 280px', maxWidth: 520 }}>
          <span className="search-bar-icon" aria-hidden><IconSearch size={16} /></span>
          <input
            className="form-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Find a test in your reports (e.g. SWASTHFIT SUPER, Vitamin D)…"
            aria-label="Find a test in your reports"
          />
        </div>
        <button type="submit" className="btn btn-secondary btn-sm" disabled={searching}>
          {searching ? 'Finding…' : 'Find'}
        </button>
        {(hits !== null || activeQuery) && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={clear}>Clear</button>
        )}
      </form>

      {error && <div className="alert alert-error" style={{ marginTop: 'var(--space-3)' }}>{error}</div>}

      {hits !== null && hits.length === 0 && (
        <p className="form-hint" style={{ marginTop: 'var(--space-3)' }}>No results match “{activeQuery}”.</p>
      )}

      {hits !== null && hits.length > 0 && (
        <>
          <p className="form-hint" style={{ margin: 'var(--space-3) 0' }}>
            {truncated ? `First ${hits.length}` : hits.length} result{hits.length === 1 ? '' : 's'} in {reportCount}{' '}
            report{reportCount === 1 ? '' : 's'}
          </p>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Date</th>
                  <th>Test</th>
                  <th>Value</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {hits.map(hit => (
                  <tr key={hit.id}>
                    <td>
                      <Link to={`/medical-reports/${hit.report.id}`}>{hit.report.title}</Link>
                    </td>
                    <td className="font-mono">
                      {hit.report.report_date ? new Date(`${hit.report.report_date}T00:00:00`).toLocaleDateString() : '—'}
                    </td>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{hit.test_name}</td>
                    <td className="font-mono">{hit.value}{hit.unit ? ` ${hit.unit}` : ''}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        aria-label={`Delete ${hit.test_name} from ${hit.report.title}`}
                        disabled={deletingId !== null}
                        onClick={() => remove(hit)}
                      >
                        <IconTrash size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export default TestResultSearch;
