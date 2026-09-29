import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiService } from '../services/api';
import type { HealthTrendParameter, LabTestType, TestNameLink, TestNameLinkSuggestion } from '../services/api';
import { apiErrorMessage } from '../utils/apiErrors';

const MAX_SUGGEST_NAMES = 50;

interface TestNameLinksProps {
  parameters: HealthTrendParameter[];
  /** Called after a link is saved or removed, since results then move between trends. */
  onChanged: () => void;
  /** Looks a printed name up without leaving the page; without it, Find opens the Medical Reports page. */
  onFind?: (name: string) => void;
}

/**
 * Printed test names that match no catalog test, and the user's links from such names to catalog tests.
 * The AI can suggest a test for each name; nothing is linked until the user confirms it.
 */
const TestNameLinks: React.FC<TestNameLinksProps> = ({ parameters, onChanged, onFind }) => {
  const [catalog, setCatalog] = useState<LabTestType[]>([]);
  const [links, setLinks] = useState<TestNameLink[]>([]);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [suggestions, setSuggestions] = useState<Record<string, TestNameLinkSuggestion>>({});
  const [suggesting, setSuggesting] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);
  // Shown under the row the user acted on, which may be far below the card's own message.
  const [rowMessages, setRowMessages] = useState<Record<string, { kind: 'success' | 'info' | 'error'; text: string }>>({});

  // A name whose results are all qualitative ("Negative", "Absent") cannot join a catalog test's trend.
  const unlinked = useMemo(
    () => parameters.filter(parameter => !parameter.test_type && parameter.numeric_count > 0),
    [parameters],
  );

  const loadLinks = useCallback(async () => {
    try {
      setLinks(await apiService.getTestNameLinks());
    } catch {
      /* the list of unlinked names still works */
    }
  }, []);

  useEffect(() => {
    apiService
      .getAllLabTestTypes()
      .then(types => setCatalog([...types].sort((a, b) => a.display_name.localeCompare(b.display_name))))
      .catch(() => { /* the AI suggestions still show */ });
    loadLinks();
  }, [loadLinks]);

  const suggest = async () => {
    setSuggesting(true);
    setMessage(null);
    try {
      const names = unlinked.slice(0, MAX_SUGGEST_NAMES).map(parameter => parameter.name);
      const { suggestions: items } = await apiService.suggestTestNameLinks(names);
      const byName: Record<string, TestNameLinkSuggestion> = {};
      const picked: Record<string, string> = {};
      for (const item of items) {
        byName[item.name] = item;
        if (item.test_type) picked[item.name] = item.test_type;
      }
      setSuggestions(byName);
      // A test the user already picked by hand wins over the suggestion.
      setChoices(previous => ({ ...picked, ...previous }));
      const found = items.filter(item => item.test_type).length;
      setMessage({
        kind: 'success',
        text: found
          ? `AI suggested a test for ${found} of ${items.length} names. Check each one, then link it.`
          : 'AI found no catalog test for these names.',
      });
    } catch (err) {
      setMessage({ kind: 'error', text: apiErrorMessage(err, 'Could not get suggestions') });
    } finally {
      setSuggesting(false);
    }
  };

  const link = async (name: string) => {
    const testType = choices[name];
    if (!testType) return;
    setBusy(name);
    setMessage(null);
    try {
      const { alias, relinked } = await apiService.createTestNameLink(name, testType);
      setRowMessages(previous => ({
        ...previous,
        [name]: relinked
          ? { kind: 'success', text: `Linked to ${alias.test_type_display_name}; ${relinked} result${relinked === 1 ? '' : 's'} updated.` }
          : {
              kind: 'info',
              text: `Link saved, but no result changed: ${alias.test_type_display_name} does not fit the section of the report these results are in (for example a urine section). Use Find to check the reports.`,
            },
      }));
      await loadLinks();
      onChanged();
    } catch (err) {
      setRowMessages(previous => ({
        ...previous,
        [name]: { kind: 'error', text: apiErrorMessage(err, 'Could not link this name') },
      }));
    } finally {
      setBusy(null);
    }
  };

  const dismiss = (name: string) => {
    const withoutName = <T,>(record: Record<string, T>) => {
      const next = { ...record };
      delete next[name];
      return next;
    };
    setSuggestions(withoutName);
    setChoices(withoutName);
  };

  const unlink = async (item: TestNameLink) => {
    setBusy(`link-${item.id}`);
    setMessage(null);
    try {
      const { relinked } = await apiService.deleteTestNameLink(item.id);
      setMessage({
        kind: 'success',
        text: `Removed the link for “${item.name}”; ${relinked} result${relinked === 1 ? '' : 's'} updated.`,
      });
      await loadLinks();
      onChanged();
    } catch (err) {
      setMessage({ kind: 'error', text: apiErrorMessage(err, 'Could not remove this link') });
    } finally {
      setBusy(null);
    }
  };

  if (unlinked.length === 0 && links.length === 0) return null;

  const mutedText: React.CSSProperties = { fontSize: 'var(--font-xs)', color: 'var(--text-muted)' };

  return (
    <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
      <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
        <div>
          <h3 style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>Tests not linked to the catalog</h3>
          <p style={{ ...mutedText, marginTop: 'var(--space-1)' }}>
            Link a printed name to a catalog test so its results join that test’s trend. Links apply to your reports only.
          </p>
        </div>
        {unlinked.length > 0 && (
          <button className="btn btn-secondary btn-sm" onClick={suggest} disabled={suggesting || busy !== null}>
            {suggesting
              ? 'Asking AI…'
              : unlinked.length > MAX_SUGGEST_NAMES ? `Suggest with AI (first ${MAX_SUGGEST_NAMES})` : 'Suggest with AI'}
          </button>
        )}
      </div>

      {message && (
        <div className={`alert alert-${message.kind}`} role="status" style={{ marginBottom: 'var(--space-4)' }}>
          {message.text}
        </div>
      )}

      {unlinked.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Printed name</th>
                <th>Results</th>
                <th>Catalog test</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {unlinked.map(parameter => {
                const suggestion = suggestions[parameter.name];
                return (
                  <tr key={parameter.key}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{parameter.name}</td>
                    <td>{parameter.result_count}</td>
                    <td>
                      <select
                        className="form-select"
                        value={choices[parameter.name] ?? ''}
                        onChange={e => setChoices(previous => ({ ...previous, [parameter.name]: e.target.value }))}
                        aria-label={`Catalog test for ${parameter.name}`}
                      >
                        <option value="">Not linked</option>
                        {catalog.map(testType => (
                          <option key={testType.name} value={testType.name}>{testType.display_name}</option>
                        ))}
                      </select>
                      {suggestion && (
                        <div style={{ ...mutedText, marginTop: 'var(--space-1)' }}>
                          AI: {suggestion.test_type_display_name ?? 'no matching test'}
                          {suggestion.reason ? ` — ${suggestion.reason}` : ''}
                        </div>
                      )}
                      {rowMessages[parameter.name] && (
                        <div
                          role="status"
                          style={{
                            ...mutedText,
                            marginTop: 'var(--space-1)',
                            color: { success: 'var(--sage)', info: 'var(--text-secondary)', error: 'var(--coral)' }[
                              rowMessages[parameter.name].kind
                            ],
                          }}
                        >
                          {rowMessages[parameter.name].text}
                        </div>
                      )}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={!choices[parameter.name] || busy !== null}
                        onClick={() => link(parameter.name)}
                      >
                        {busy === parameter.name ? 'Linking…' : 'Link'}
                      </button>
                      {onFind ? (
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ marginLeft: 'var(--space-2)' }}
                          title="Find the reports these results are in"
                          onClick={() => onFind(parameter.name)}
                        >
                          Find
                        </button>
                      ) : (
                        <Link
                          to={`/medical-reports?test=${encodeURIComponent(parameter.name)}`}
                          className="btn btn-ghost btn-sm"
                          style={{ marginLeft: 'var(--space-2)' }}
                          title="Find the reports these results are in"
                        >
                          Find
                        </Link>
                      )}
                      {suggestion && (
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ marginLeft: 'var(--space-2)' }}
                          onClick={() => dismiss(parameter.name)}
                        >
                          Dismiss
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {links.length > 0 && (
        <div style={{ marginTop: unlinked.length > 0 ? 'var(--space-6)' : 0 }}>
          <h4 style={{ fontSize: 'var(--font-sm)', fontWeight: 600, marginBottom: 'var(--space-2)' }}>Your name links</h4>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 'var(--space-2)' }}>
            {links.map(item => (
              <li key={item.id} className="row-between" style={{ gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                <span>
                  “{item.name}” → <strong>{item.test_type_display_name}</strong>
                </span>
                <button className="btn btn-ghost btn-sm" disabled={busy !== null} onClick={() => unlink(item)}>
                  {busy === `link-${item.id}` ? 'Removing…' : 'Remove'}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default TestNameLinks;
