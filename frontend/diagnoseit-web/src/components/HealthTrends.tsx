import React, { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiService } from '../services/api';
import type { HealthTrendData, HealthTrendParameter, HealthTrendPoint, TrendSelection } from '../services/api';
import { apiErrorMessage } from '../utils/apiErrors';
import { copyText } from '../utils/clipboard';
import { useToast } from '../contexts/ToastContext';
import {
  SERIES_COLORS,
  drawTrendChart,
  plottablePoints,
  type ChartLayout,
  type ChartPoint,
  type TrendLayoutMode,
  type TrendScaleMode,
  type TrendSeries,
} from '../utils/trendChart';
import { IconCopy, IconSearch, IconTrends } from './Icons';
import TestNameLinks from './TestNameLinks';
import TestResultSearch from './TestResultSearch';

/** As many tests as the endpoint will chart at once, and as many colours as stay apart on one chart. */
const MAX_SERIES = 6;

/** A test the user picked to chart, in the order they picked it. `key` matches the trend the API returns. */
interface TrendPick {
  key: string;
  name: string;
  selection: TrendSelection;
}

type HoveredPoint = ChartPoint & { width: number };

function pickFromParameter(parameter: HealthTrendParameter): TrendPick {
  return {
    key: parameter.key,
    name: parameter.name,
    // A name the catalog does not know shows only its own results, not the catalog test it resembles.
    selection: parameter.test_type
      ? { kind: 'test_type', value: parameter.test_type }
      : { kind: 'name', value: parameter.name },
  };
}

/** Unit spellings that mean the same thing ("mg/dl", "mg/dL") must not force an indexed scale. */
function sameUnit(a: string, b: string): boolean {
  const tidy = (unit: string) => unit.replace(/\s+/g, '').replace(/[µμ]/g, 'u').toLowerCase();
  return tidy(a) === tidy(b);
}

const HealthTrends: React.FC = () => {
  const { toast } = useToast();
  const [searchTerm, setSearchTerm] = useState('');
  const [picks, setPicks] = useState<TrendPick[]>([]);
  const [series, setSeries] = useState<HealthTrendData[]>([]);
  const [loading, setLoading] = useState(true);
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [availableTests, setAvailableTests] = useState<HealthTrendParameter[]>([]);
  const [layout, setLayout] = useState<TrendLayoutMode>('overlay');
  // 'auto' keeps real values while the tests share a unit, and indexes them when they do not.
  const [scaleChoice, setScaleChoice] = useState<TrendScaleMode | 'auto'>('auto');
  // The test finder below keeps its query here, so Find on an unlinked name searches without leaving.
  const [, setSearchParams] = useSearchParams();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const layoutRef = useRef<ChartLayout | null>(null);
  const [hovered, setHovered] = useState<HoveredPoint | null>(null);
  const [selected, setSelected] = useState<{ point: HealthTrendPoint; key: string } | null>(null);

  const seriesByKey = useMemo(() => new Map(series.map(item => [item.key, item])), [series]);

  const filteredTests = useMemo(() => {
    const words = searchTerm.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    if (words.length === 0) return availableTests;
    return availableTests.filter(parameter => {
      const searchable = [parameter.name, parameter.test_type ?? '', ...parameter.printed_names]
        .join(' ')
        .toLocaleLowerCase();
      return words.every(word => searchable.includes(word));
    });
  }, [availableTests, searchTerm]);

  /** The picked tests with their data and colour, in the order they were picked. */
  const charted = useMemo(
    () =>
      picks.map((pick, index) => {
        const data = seriesByKey.get(pick.key);
        // A result printed in a unit that could not be converted would plot on the wrong scale.
        const points = data ? plottablePoints(data.trends) : [];
        return {
          pick,
          data,
          points,
          color: SERIES_COLORS[index % SERIES_COLORS.length],
          unit: data?.unit ?? '',
        };
      }),
    [picks, seriesByKey],
  );

  const drawable = useMemo(() => charted.filter(item => item.points.length > 0), [charted]);
  const single = charted.length === 1 ? charted[0] : null;

  const scale: TrendScaleMode = useMemo(() => {
    if (scaleChoice !== 'auto') return scaleChoice;
    const units = drawable.map(item => item.unit);
    return units.every(unit => sameUnit(unit, units[0] ?? '')) ? 'value' : 'indexed';
  }, [scaleChoice, drawable]);

  const chartSeries: TrendSeries[] = useMemo(
    () =>
      drawable.map(item => ({
        key: item.pick.key,
        label: item.pick.name,
        unit: item.unit,
        color: item.color,
        points: item.points,
      })),
    [drawable],
  );

  // One entry per catalog test, so printed variants ("ALT (SGPT)", "ALT (SGPT), SERUM") share a chart.
  const loadParameters = useCallback(async () => {
    try {
      setAvailableTests(await apiService.getHealthTrendParameters());
    } catch {
      /* the search box still works */
    }
  }, []);

  useEffect(() => {
    loadParameters().finally(() => setLoading(false));
  }, [loadParameters]);

  useEffect(() => {
    if (picks.length === 0) {
      setSeries([]);
      return;
    }
    let current = true;
    setSeriesLoading(true);
    apiService
      .getMultiHealthTrends(picks.map(pick => pick.selection))
      .then(loaded => {
        if (current) {
          setSeries(loaded);
          setError(null);
        }
      })
      .catch(err => {
        if (current) {
          setSeries([]);
          setError(apiErrorMessage(err, 'Could not load these trends'));
        }
      })
      .finally(() => {
        if (current) setSeriesLoading(false);
      });
    return () => {
      current = false;
    };
  }, [picks]);

  const togglePick = (parameter: HealthTrendParameter) => {
    setError(null);
    setSelected(null);
    setPicks(current => {
      if (current.some(pick => pick.key === parameter.key)) {
        return current.filter(pick => pick.key !== parameter.key);
      }
      if (current.length >= MAX_SERIES) {
        setError(`Chart at most ${MAX_SERIES} tests at a time. Remove one first.`);
        return current;
      }
      return [...current, pickFromParameter(parameter)];
    });
  };

  const removePick = (key: string) => {
    setError(null);
    setSelected(null);
    setPicks(current => current.filter(pick => pick.key !== key));
  };

  // Stacked panels need room: each test gets its own strip under the one above it.
  const chartHeight = layout === 'stacked' ? Math.max(320, drawable.length * 130 + 60) : 320;

  const scheduleDraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (chartSeries.length === 0) {
      const ctx = canvas.getContext('2d');
      const wrapper = canvas.parentElement;
      if (wrapper && ctx) {
        const dpr = window.devicePixelRatio || 1;
        const rect = wrapper.getBoundingClientRect();
        canvas.width = Math.max(1, Math.floor(rect.width * dpr));
        canvas.height = Math.max(1, Math.floor(rect.height * dpr));
        canvas.style.width = `${Math.max(1, rect.width)}px`;
        canvas.style.height = `${Math.max(1, rect.height)}px`;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      layoutRef.current = null;
      setHovered(null);
      return;
    }

    layoutRef.current = drawTrendChart(canvas, chartSeries, { layout, scale });
    setHovered(null);
  }, [chartSeries, layout, scale]);

  // After layout so the chart wrapper has non-zero width (flex/grid first paint).
  useLayoutEffect(() => {
    let raf1 = 0;
    let raf2 = 0;
    raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => scheduleDraw());
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, [scheduleDraw, chartHeight]);

  useEffect(() => {
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => scheduleDraw()) : null;
    const el = canvasRef.current?.parentElement;
    if (ro && el) ro.observe(el);
    const handleResize = () => scheduleDraw();
    window.addEventListener('resize', handleResize);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', handleResize);
    };
  }, [scheduleDraw]);

  // Show the point nearest the pointer, so a point is easy to hit on a dense chart.
  const nearestPoint = (e: React.MouseEvent<HTMLCanvasElement>): ChartPoint | null => {
    const chart = layoutRef.current;
    if (!chart || chart.points.length === 0) return null;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // Distance counts the vertical gap too, so stacked panels and crossing lines pick the right point.
    const distance = (point: ChartPoint) => Math.hypot(point.x - x, (point.y - y) * 0.6);
    const nearest = chart.points.reduce((best, point) => (distance(point) < distance(best) ? point : best));
    return distance(nearest) <= 40 ? nearest : null;
  };

  const showNearestPoint = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const point = nearestPoint(e);
    setHovered(point ? { ...point, width: layoutRef.current!.width } : null);
  };

  const selectNearestPoint = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const point = nearestPoint(e);
    if (point) selectPoint(point.trend, point.seriesKey);
  };

  const selectPoint = (point: HealthTrendPoint, key: string) => {
    setSelected({ point, key });
    window.setTimeout(() => document.getElementById('trend-explanation')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 0);
  };

  const statusBadge = (status: string) => {
    const map: Record<string, string> = {
      NORMAL: 'badge-success', HIGH: 'badge-danger',
      LOW: 'badge-warning', ABNORMAL: 'badge-danger',
    };
    return map[status] || 'badge-muted';
  };

  /** Every date any of the charted tests has a result on, oldest first. */
  const allDates = useMemo(() => {
    const dates = new Set<string>();
    for (const item of charted) {
      for (const point of item.data?.trends ?? []) {
        if (point.date) dates.add(point.date);
      }
    }
    return [...dates].sort();
  }, [charted]);

  /** Every result each charted test has on each date. A date can have more than one report. */
  const pointsByDate = useMemo(() => {
    const rows = new Map<string, Map<string, HealthTrendPoint[]>>();
    for (const item of charted) {
      const column = new Map<string, HealthTrendPoint[]>();
      for (const point of item.data?.trends ?? []) {
        if (point.date) column.set(point.date, [...(column.get(point.date) ?? []), point]);
      }
      rows.set(item.pick.key, column);
    }
    return rows;
  }, [charted]);

  /** Repeat a date enough times to show the largest number of same-day readings in any column. */
  const tableRows = useMemo(
    () => allDates.flatMap(date => {
      const count = Math.max(
        1,
        ...charted.map(item => pointsByDate.get(item.pick.key)?.get(date)?.length ?? 0),
      );
      return Array.from({ length: count }, (_, index) => ({ date, index }));
    }),
    [allDates, charted, pointsByDate],
  );

  const exportCSV = () => {
    if (charted.length === 0) return;
    let csv: string;
    let filename: string;
    const quote = (text: string) => `"${String(text ?? '').replace(/"/g, '""')}"`;

    if (single?.data) {
      const headers = 'Date,Value,Unit,Status,Reference Range,Printed Value,Printed Unit,Printed Reference Range';
      const rows = single.data.trends.map(t =>
        `${t.date},${t.value},${t.unit},${t.status},"${t.reference_range}",${t.original_value},${t.original_unit},"${t.original_reference_range}"`
      );
      csv = [headers, ...rows].join('\n');
      filename = `${single.data.parameter}_trends.csv`;
    } else {
      // One column per test, so the dates line up the way the chart does.
      const headers = ['Date', ...charted.map(item => quote(`${item.pick.name}${item.unit ? ` (${item.unit})` : ''}`))];
      const rows = tableRows.map(row =>
        [row.date, ...charted.map(item => quote(pointsByDate.get(item.pick.key)?.get(row.date)?.[row.index]?.value ?? ''))].join(',')
      );
      csv = [headers.join(','), ...rows].join('\n');
      filename = `health_trends_${charted.length}_tests.csv`;
    }

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  /** Tab-separated text pastes into a spreadsheet with the same rows and columns as the visible table. */
  const copyTable = async () => {
    const clean = (value: unknown) => String(value ?? '').replace(/[\t\r\n]+/g, ' ').trim();
    let rows: string[][];

    if (single?.data) {
      rows = [
        ['Date', 'Report', 'Value', 'Unit', 'Reference Range', 'Status'],
        ...single.data.trends.map(point => [
          point.date,
          point.report_title,
          point.value,
          point.unit,
          point.reference_range,
          point.status,
        ]),
      ];
    } else {
      rows = [
        ['Date', ...charted.map(item => `${item.pick.name}${item.unit ? ` (${item.unit})` : ''}`)],
        ...tableRows.map(row => [
          row.date,
          ...charted.map(item => {
            const point = pointsByDate.get(item.pick.key)?.get(row.date)?.[row.index];
            if (!point) return '';
            const status = point.status && point.status !== 'NORMAL' ? point.status : '';
            return [point.value, status, point.report_title].filter(Boolean).join(' · ');
          }),
        ]),
      ];
    }

    const copied = await copyText(rows.map(row => row.map(clean).join('\t')).join('\n'));
    toast(copied ? 'Data points copied' : 'Could not copy the data points', copied ? 'success' : 'error');
  };

  if (loading) {
    return (
      <div className="stack">
        <div className="skeleton" style={{ height: 48, width: 280 }} />
        <div className="skeleton" style={{ height: 320 }} />
        <div className="skeleton" style={{ height: 200 }} />
      </div>
    );
  }

  const totalPoints = charted.reduce((sum, item) => sum + (item.data?.trends.length ?? 0), 0);
  const plottedPoints = drawable.reduce((sum, item) => sum + item.points.length, 0);
  const unconverted = charted.reduce((sum, item) => sum + (item.data?.unconverted_count ?? 0), 0);
  const converted = charted.reduce(
    (sum, item) => sum + (item.data?.trends.filter(t => t.unit_status === 'converted').length ?? 0),
    0,
  );
  const waiting = seriesLoading && series.length === 0;

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Health Trends</h1>
          <p className="page-subtitle">Track how your test results change over time, one test or several together</p>
        </div>
        {totalPoints > 0 && (
          <button className="btn btn-secondary btn-sm" onClick={exportCSV}>
            Export CSV
          </button>
        )}
      </div>

      {/* Search */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <div className="search-bar" style={{ maxWidth: 500 }}>
          <span className="search-bar-icon" aria-hidden><IconSearch size={16} /></span>
          <input
            aria-label="Search for a test parameter"
            className="form-input"
            placeholder="Search for a test parameter (e.g. Hemoglobin, Glucose)…"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            id="health-trend-search"
          />
        </div>
      </div>

      {error && (
        <div className="chart-unplottable-notice" role="alert" style={{ marginBottom: 'var(--space-4)' }}>
          {error}
        </div>
      )}

      {/* Quick pick from available tests; picking a second test charts it beside the first. */}
      {availableTests.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
          <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
            <h3 style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>
              Available Test Parameters
            </h3>
            <span style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)' }}>
              {searchTerm.trim()
                ? `${filteredTests.length} of ${availableTests.length} shown`
                : picks.length > 0
                  ? `${picks.length} of ${MAX_SERIES} charted · click a test to add or remove it`
                  : `Click a test to chart it, then up to ${MAX_SERIES - 1} more to compare`}
            </span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            {filteredTests.map(parameter => {
              const index = picks.findIndex(pick => pick.key === parameter.key);
              const chosen = index !== -1;
              return (
                <button
                  key={parameter.key}
                  className={`btn btn-sm ${chosen ? 'btn-primary' : 'btn-secondary'}`}
                  aria-pressed={chosen}
                  onClick={() => togglePick(parameter)}
                  title={parameter.printed_names.length > 1 ? `Printed as: ${parameter.printed_names.join(', ')}` : undefined}
                >
                  {chosen && (
                    <span
                      className="chart-legend-dot"
                      style={{ background: SERIES_COLORS[index % SERIES_COLORS.length], marginRight: 'var(--space-2)' }}
                      aria-hidden
                    />
                  )}
                  {parameter.name}
                  <span style={{ opacity: 0.7, marginLeft: 'var(--space-1)' }}>{parameter.result_count}</span>
                </button>
              );
            })}
            {filteredTests.length === 0 && (
              <span className="form-hint">No test parameters match “{searchTerm.trim()}”.</span>
            )}
          </div>
        </div>
      )}

      {/* Which reports a test appears in, and a way to delete rows that are not tests at all. */}
      <TestResultSearch
        heading="Find a test in your reports"
        hint="See which reports a test appears in, and remove rows that are not really tests."
        onResultDeleted={loadParameters}
      />

      {picks.length === 0 && (
        <TestNameLinks
          parameters={availableTests}
          onChanged={loadParameters}
          onFind={name => setSearchParams(previous => {
            const next = new URLSearchParams(previous);
            next.set('test', name);
            return next;
          }, { replace: true })}
        />
      )}

      {/* Loading spinner, while the first trends of a selection are on their way */}
      {waiting && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--space-12)' }}>
          <div className="spinner spinner-lg" />
        </div>
      )}

      {/* Chart */}
      {picks.length > 0 && !waiting && (
        <>
          {totalPoints === 0 ? (
            <div className="chart-card">
              <div className="chart-empty">
                <div className="chart-empty-icon"><IconTrends size={32} /></div>
                <p>
                  No data found for {charted.map(item => <strong key={item.pick.key}>"{item.pick.name}" </strong>)}
                </p>
                <p style={{ fontSize: 'var(--font-xs)' }}>
                  Upload more reports with this parameter to see trends
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="chart-card">
                <div className="row-between" style={{ flexWrap: 'wrap', gap: 'var(--space-3)' }}>
                  <div>
                    <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 600 }}>
                      <span className="text-gradient">
                        {charted.map(item => item.pick.name).join(' · ')}
                      </span>{' '}
                      over time
                    </h3>
                    <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                      {totalPoints} data point{totalPoints !== 1 ? 's' : ''}
                      {plottedPoints > 0 && plottedPoints < totalPoints ? ` (${plottedPoints} plottable)` : ''}
                      {single?.data?.unit && ` · Unit: ${single.data.unit}`}
                      {converted > 0 && ` · ${converted} converted from another unit`}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                    {drawable.length > 1 && (
                      <>
                        <select
                          aria-label="How the tests are laid out"
                          className="form-select form-select-sm"
                          value={layout}
                          onChange={e => setLayout(e.target.value as TrendLayoutMode)}
                        >
                          <option value="overlay">Stacked on one chart</option>
                          <option value="stacked">One panel each</option>
                        </select>
                        {layout === 'overlay' && (
                          <select
                            aria-label="How the values are scaled"
                            className="form-select form-select-sm"
                            value={scaleChoice}
                            onChange={e => setScaleChoice(e.target.value as TrendScaleMode | 'auto')}
                          >
                            <option value="auto">Scale: automatic</option>
                            <option value="value">Scale: real values</option>
                            <option value="indexed">Scale: indexed (0–100%)</option>
                          </select>
                        )}
                      </>
                    )}
                    <button className="btn btn-secondary btn-sm" onClick={() => { setPicks([]); setSearchTerm(''); }}>
                      ← Back to search
                    </button>
                  </div>
                </div>

                {plottedPoints === 0 && (
                  <div className="chart-unplottable-notice" role="status">
                    These values are text or qualitative (for example “Negative” or “Trace”), so no numeric trend line
                    can be drawn. Use the table below; you can still export CSV.
                  </div>
                )}

                {unconverted > 0 && (
                  <div className="chart-unplottable-notice" role="status">
                    {unconverted} result{unconverted !== 1 ? 's are' : ' is'} printed in another unit with no known
                    conversion, so {unconverted !== 1 ? 'they are' : 'it is'} not plotted. See the table below.
                  </div>
                )}

                {drawable.length > 1 && layout === 'overlay' && scale === 'indexed' && (
                  <div className="chart-unplottable-notice" role="status">
                    These tests are measured in different units, so each line is drawn over its own range —
                    0% is that test's lowest result and 100% its highest. Compare the shapes, not the heights.
                    The legend and the table below give the real values.
                  </div>
                )}

                  {plottedPoints > 0 && <p className="form-hint">Click a chart point or a value in the table to see its source.</p>}
                  <div className="chart-canvas-wrapper" style={{ height: chartHeight }}>
                  <canvas
                    ref={canvasRef}
                    aria-hidden={plottedPoints === 0}
                    onMouseMove={showNearestPoint}
                    onClick={selectNearestPoint}
                    onMouseLeave={() => setHovered(null)}
                  />
                  {hovered && (
                    <div
                      className="chart-tooltip"
                      role="status"
                      style={{ left: Math.min(Math.max(hovered.x, 90), hovered.width - 90), top: hovered.y }}
                    >
                      {charted.length > 1 && (
                        <span style={{ color: hovered.color, fontWeight: 600 }}>{hovered.label}</span>
                      )}
                      <strong className="font-mono">
                        {hovered.trend.value}{hovered.trend.unit ? ` ${hovered.trend.unit}` : ''}
                      </strong>
                      <span>{new Date(`${hovered.trend.date}T00:00:00`).toLocaleDateString()}</span>
                      {hovered.trend.status && <span>{hovered.trend.status}</span>}
                      {hovered.trend.unit_status === 'converted' && (
                        <span>printed {hovered.trend.original_value} {hovered.trend.original_unit}</span>
                      )}
                    </div>
                  )}
                </div>

                {selected && (
                  <div id="trend-explanation" className="trend-explanation card" role="region" aria-label="Selected trend result">
                    <div className="row-between" style={{ gap: 'var(--space-3)' }}>
                      <div>
                        <p className="eyebrow">Selected result · {selected.point.date}</p>
                        <h3>{selected.point.printed_name}</h3>
                      </div>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelected(null)} aria-label="Close result details">✕</button>
                    </div>
                    <div className="trend-explanation-values">
                      <div><span>Saved result</span><strong>{selected.point.original_value} {selected.point.original_unit}</strong></div>
                      <div><span>Trend value</span><strong>{selected.point.value} {selected.point.unit}</strong></div>
                    </div>
                    <p className="form-hint">
                      {selected.point.unit_status === 'converted'
                        ? `Converted to ${selected.point.unit}, the unit used by most results in this trend.`
                        : selected.point.unit_status === 'unconverted'
                          ? 'No conversion is available for this unit, so this result is listed but not plotted.'
                          : 'The chart uses the stored value and unit.'}
                      {seriesByKey.get(selected.key)?.test_type
                        ? ` Linked to ${seriesByKey.get(selected.key)?.parameter} in the lab catalog.`
                        : ' Listed under its printed name; it is not linked to a catalog test.'}
                      {' '}Compare the saved result with the PDF to check what the lab printed.
                    </p>
                    <Link className="btn btn-secondary btn-sm" to={`/medical-reports/${selected.point.report_id}?result=${selected.point.result_id}`}>
                      Open {selected.point.report_title} at this result →
                    </Link>
                  </div>
                )}

                <div className="chart-legend">
                  {charted.map(item => (
                    <div className="chart-legend-item" key={item.pick.key}>
                      <div className="chart-legend-dot" style={{ background: item.color }} />
                      <span>
                        {item.pick.name}
                        {item.unit ? ` · ${item.unit}` : ''}
                        {item.data && item.data.trends.length > 0
                          ? ` · ${item.points.length}/${item.data.trends.length}`
                          : ' · no results'}
                      </span>
                      <button
                        className="btn-ghost chart-legend-remove"
                        onClick={() => removePick(item.pick.key)}
                        aria-label={`Remove ${item.pick.name} from the chart`}
                        title={`Remove ${item.pick.name} from the chart`}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  {single && (
                    <div className="chart-legend-item">
                      <div className="chart-legend-dot" style={{ background: 'rgba(74, 124, 89, 0.45)' }} />
                      <span>Reference Range</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Data Table */}
              <div className="card" style={{ marginTop: 'var(--space-4)' }}>
                <div className="row-between" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
                  <h3 style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>Data Points</h3>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={copyTable}>
                    <IconCopy size={14} /> Copy table
                  </button>
                </div>
                <div className="table-wrapper">
                  {single?.data ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Report</th>
                          <th>Value</th>
                          <th>Unit</th>
                          <th>Reference Range</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {single.data.trends.map((t, i) => (
                          <tr key={`${t.report_id}-${i}`}>
                            <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                              <Link className="trend-point-link" to={`/medical-reports/${t.report_id}`}>
                                {new Date(`${t.date}T00:00:00`).toLocaleDateString()}
                              </Link>
                            </td>
                            <td>
                              <Link className="trend-point-link" to={`/medical-reports/${t.report_id}`}>
                                {t.report_title}
                              </Link>
                            </td>
                            <td style={{ fontWeight: 600, fontFamily: 'monospace' }}>
                              <button type="button" className="trend-point-link trend-point-button" onClick={() => selectPoint(t, single.pick.key)} aria-label={`Explain ${single.pick.name} result from ${t.report_title}`}>
                                {t.value}
                                {t.unit_status === 'converted' && (
                                  <span className="trend-point-detail">saved {t.original_value} {t.original_unit}</span>
                                )}
                              </button>
                            </td>
                            <td>
                              {t.unit}
                              {t.unit_status === 'unconverted' && (
                                <span className="badge badge-muted" style={{ marginLeft: 'var(--space-2)' }}>not plotted</span>
                              )}
                            </td>
                            <td>{t.reference_range || '—'}</td>
                            <td>
                              <span className={`badge ${statusBadge(t.status)}`}>
                                {t.status || 'Unknown'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    // One row per date and one column per test, so the same reading lines up across tests.
                    <table>
                      <thead>
                        <tr>
                          <th>Date</th>
                          {charted.map(item => (
                            <th key={item.pick.key}>
                              <span
                                className="chart-legend-dot"
                                style={{ background: item.color, marginRight: 6, display: 'inline-block' }}
                                aria-hidden
                              />
                              {item.pick.name}
                              {item.unit ? <span style={{ color: 'var(--text-muted)' }}> ({item.unit})</span> : null}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {tableRows.map(row => (
                          <tr key={`${row.date}-${row.index}`}>
                            <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                              {new Date(`${row.date}T00:00:00`).toLocaleDateString()}
                            </td>
                            {charted.map(item => {
                              const point = pointsByDate.get(item.pick.key)?.get(row.date)?.[row.index];
                              if (!point) return <td key={item.pick.key} style={{ color: 'var(--text-muted)' }}>—</td>;
                              return (
                                <td key={item.pick.key} style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                                  <button
                                    type="button"
                                    className="trend-point-link trend-point-button"
                                    onClick={() => selectPoint(point, item.pick.key)}
                                    aria-label={`Explain ${item.pick.name} result from ${point.report_title}`}
                                  >
                                    {point.value}
                                    {point.status && point.status !== 'NORMAL' && (
                                      <span className={`badge ${statusBadge(point.status)}`} style={{ marginLeft: 'var(--space-2)' }}>
                                        {point.status}
                                      </span>
                                    )}
                                    {point.unit_status === 'unconverted' && (
                                      <span className="trend-point-detail">{point.unit} · not plotted</span>
                                    )}
                                    <span className="trend-point-detail">{point.report_title}</span>
                                  </button>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* Default empty state */}
      {picks.length === 0 && !seriesLoading && availableTests.length === 0 && (
        <div className="empty-state card">
          <div className="empty-state-icon"><IconTrends size={32} /></div>
          <div className="empty-state-title">No test data yet</div>
          <div className="empty-state-text">
            Upload medical reports with test results to start tracking health trends over time. Tests are grouped
            by the <Link to="/lab-catalog">test catalog</Link>.
          </div>
        </div>
      )}
    </div>
  );
};

export default HealthTrends;
