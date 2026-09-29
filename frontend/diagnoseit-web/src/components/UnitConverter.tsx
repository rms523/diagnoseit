import React, { useState, useEffect, useMemo } from 'react';
import { apiService } from '../services/api';
import type { LabTestType, LabTestTypeUnit, LabTestValidationResult, UnitConversionResult } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { IconSwap } from './Icons';

function validationBadgeClass(status: string): string {
  const s = status.toUpperCase();
  if (s === 'NORMAL') return 'badge-success';
  if (s.includes('HIGH') || s === 'CRITICAL_HIGH') return 'badge-danger';
  if (s.includes('LOW') || s === 'CRITICAL_LOW') return 'badge-warning';
  return 'badge-muted';
}

const UnitConverter: React.FC = () => {
  const { toast } = useToast();
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState('');
  const [tests, setTests] = useState<LabTestType[]>([]);
  const [units, setUnits] = useState<LabTestTypeUnit[]>([]);
  const [loadingTests, setLoadingTests] = useState(true);
  const [loadingUnits, setLoadingUnits] = useState(false);
  const [converting, setConverting] = useState(false);

  const [search, setSearch] = useState('');
  const [testName, setTestName] = useState('');
  const [fromUnit, setFromUnit] = useState('');
  const [toUnit, setToUnit] = useState('');
  const [value, setValue] = useState('');

  const [result, setResult] = useState<UnitConversionResult | null>(null);
  const [validation, setValidation] = useState<LabTestValidationResult | null>(null);

  useEffect(() => {
    apiService.getLabTestCategories()
      .then(cats => {
        setCategories(cats);
        if (cats.length > 0) setCategory(cats[0]);
      })
      .catch(() => toast('Failed to load test categories', 'error'))
      .finally(() => setLoadingTests(false));
  }, [toast]);

  useEffect(() => {
    if (!category) return;
    setLoadingTests(true);
    setTestName('');
    setUnits([]);
    setResult(null);
    setValidation(null);
    apiService.getAllLabTestTypes(category)
      .then(setTests)
      .catch(() => toast('Failed to load tests', 'error'))
      .finally(() => setLoadingTests(false));
  }, [category, toast]);

  useEffect(() => {
    if (!testName) {
      setUnits([]);
      setFromUnit('');
      setToUnit('');
      return;
    }
    setLoadingUnits(true);
    setResult(null);
    setValidation(null);
    apiService.getLabTestUnits(testName)
      .then(data => {
        setUnits(data);
        const test = tests.find(t => t.name === testName);
        const defaultUnit = test?.default_unit || data[0]?.unit.name || '';
        setFromUnit(defaultUnit);
        const alt = data.find(u => u.unit.name !== defaultUnit);
        setToUnit(alt?.unit.name || defaultUnit);
      })
      .catch(() => toast('Failed to load units', 'error'))
      .finally(() => setLoadingUnits(false));
  }, [testName, tests, toast]);

  const filteredTests = useMemo(() => {
    if (!search.trim()) return tests;
    const q = search.toLowerCase();
    return tests.filter(t =>
      t.display_name.toLowerCase().includes(q) ||
      t.name.toLowerCase().includes(q) ||
      t.aliases?.some(a => a.toLowerCase().includes(q))
    );
  }, [tests, search]);

  const selectedTest = tests.find(t => t.name === testName);
  const unitOptions = units.map(u => u.unit);

  const handleConvert = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testName || !fromUnit || !toUnit || !value.trim()) {
      toast('Select a test, units, and enter a value', 'error');
      return;
    }
    if (fromUnit === toUnit) {
      toast('Choose different source and target units', 'error');
      return;
    }

    setConverting(true);
    setResult(null);
    setValidation(null);
    try {
      const converted = await apiService.convertLabUnits({
        test_type: testName,
        value: value.trim(),
        from_unit: fromUnit,
        to_unit: toUnit,
      });
      setResult(converted);
      try {
        const v = await apiService.validateLabTestValue({
          test_type: testName,
          value: String(converted.converted_value),
          unit: toUnit,
        });
        setValidation(v);
      } catch {
        /* validation optional when no rules exist */
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message.replace(/^API Error: \d+ \w+ - /, '') : 'Conversion failed';
      toast(msg, 'error');
    } finally {
      setConverting(false);
    }
  };

  const swapUnits = () => {
    setFromUnit(toUnit);
    setToUnit(fromUnit);
    setResult(null);
    setValidation(null);
  };

  if (loadingTests && categories.length === 0) {
    return (
      <div className="stack">
        <div className="skeleton" style={{ height: 48, width: 280 }} />
        <div className="skeleton" style={{ height: 320 }} />
      </div>
    );
  }

  return (
    <div className="stack animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Unit converter</h1>
          <p className="page-subtitle">Convert lab values between measurement units</p>
        </div>
      </div>

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <form className="card report-section" onSubmit={handleConvert}>
          <p className="eyebrow" style={{ marginBottom: 'var(--space-4)' }}>Conversion</p>

          <div className="form-group" style={{ marginBottom: 'var(--space-4)' }}>
            <label className="form-label" htmlFor="conv-category">Category</label>
            <select
              id="conv-category"
              className="form-select"
              value={category}
              onChange={e => setCategory(e.target.value)}
            >
              {categories.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className="form-group" style={{ marginBottom: 'var(--space-4)' }}>
            <label className="form-label" htmlFor="conv-search">Search tests</label>
            <input
              id="conv-search"
              className="form-input"
              placeholder="Filter by name…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="form-group" style={{ marginBottom: 'var(--space-4)' }}>
            <label className="form-label" htmlFor="conv-test">Test</label>
            <select
              id="conv-test"
              className="form-select"
              value={testName}
              onChange={e => setTestName(e.target.value)}
              disabled={loadingTests || filteredTests.length === 0}
            >
              <option value="">Select a test</option>
              {filteredTests.map(t => (
                <option key={t.name} value={t.name}>{t.display_name}</option>
              ))}
            </select>
          </div>

          {selectedTest && (selectedTest.normal_min || selectedTest.normal_max) && (
            <p className="font-mono" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Typical range ({selectedTest.default_unit || 'default'}):{' '}
              {selectedTest.normal_min ?? '—'} – {selectedTest.normal_max ?? '—'}
            </p>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 'var(--space-3)', alignItems: 'end', marginBottom: 'var(--space-4)' }}>
            <div className="form-group">
              <label className="form-label" htmlFor="conv-from">From</label>
              <select
                id="conv-from"
                className="form-select"
                value={fromUnit}
                onChange={e => setFromUnit(e.target.value)}
                disabled={loadingUnits || unitOptions.length === 0}
              >
                {unitOptions.map(u => (
                  <option key={u.name} value={u.name}>{u.display_name || u.name}</option>
                ))}
              </select>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={swapUnits} disabled={!fromUnit || !toUnit} aria-label="Swap units">
              <IconSwap size={16} />
            </button>
            <div className="form-group">
              <label className="form-label" htmlFor="conv-to">To</label>
              <select
                id="conv-to"
                className="form-select"
                value={toUnit}
                onChange={e => setToUnit(e.target.value)}
                disabled={loadingUnits || unitOptions.length === 0}
              >
                {unitOptions.map(u => (
                  <option key={u.name} value={u.name}>{u.display_name || u.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: 'var(--space-5)' }}>
            <label className="form-label" htmlFor="conv-value">Value</label>
            <input
              id="conv-value"
              className="form-input font-mono"
              type="text"
              inputMode="decimal"
              placeholder="e.g. 5.5"
              value={value}
              onChange={e => setValue(e.target.value)}
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={converting || !testName}>
            {converting ? <><span className="spinner" /> Converting…</> : 'Convert'}
          </button>
        </form>

        <div className="stack" style={{ gap: 'var(--space-4)' }}>
          {!result ? (
            <div className="card empty-state" style={{ padding: 'var(--space-10)' }}>
              <div className="empty-state-title">Result appears here</div>
              <div className="empty-state-text">
                Pick a test and units, enter a value, then convert. Reference range validation runs on the converted result when rules exist.
              </div>
            </div>
          ) : (
            <>
              <div className="card report-section">
                <p className="eyebrow">Converted value</p>
                <div className="row" style={{ gap: 'var(--space-4)', alignItems: 'baseline', marginTop: 'var(--space-3)', flexWrap: 'wrap' }}>
                  <span className="font-mono" style={{ fontSize: 'var(--font-3xl)', fontWeight: 600, color: 'var(--teal)' }}>
                    {result.converted_value}
                  </span>
                  <span style={{ fontSize: 'var(--font-lg)', color: 'var(--text-secondary)' }}>{result.converted_unit}</span>
                </div>
                <p className="font-mono" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 'var(--space-4)' }}>
                  {result.original_value} {result.original_unit} → {result.converted_value} {result.converted_unit}
                </p>
                <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginTop: 'var(--space-3)' }}>
                  {result.formula}
                </p>
              </div>

              {validation && (
                <div className="card">
                  <p className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>Reference check</p>
                  <div className="row" style={{ gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span className={`badge ${validationBadgeClass(validation.status)}`}>{validation.status}</span>
                    <span style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)' }}>{validation.message}</span>
                  </div>
                  {validation.normal_range && (
                    <p className="font-mono" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 'var(--space-3)' }}>
                      Normal: {validation.normal_range}
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default UnitConverter;
