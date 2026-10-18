import React, { useEffect, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { HealthTrendData, HealthTrendPoint, User } from '../services/api';
import {
  drawTrendChart,
  isOutOfRange,
  resultFlag,
  type TrendLayoutMode,
  type TrendScaleMode,
  type TrendSeries,
} from '../utils/trendChart';

/** One charted test, as the Health Trends page holds it. */
export interface PrintedTrend {
  key: string;
  name: string;
  unit: string;
  color: string;
  data?: HealthTrendData;
}

/** 'perTest': a table for each test. 'combined': one table, a row per date and a column per test. */
export type PrintTables = 'perTest' | 'combined';
/** 'grid': a small chart per test, whatever the screen shows. 'screen': the chart as laid out on screen. */
export type PrintChart = 'grid' | 'screen';

interface Props {
  trends: PrintedTrend[];
  chartSeries: TrendSeries[];
  layout: TrendLayoutMode;
  scale: TrendScaleMode;
  tables: PrintTables;
  chart: PrintChart;
  user: User | null;
}

/** A combined table wider than this many tests is printed on a landscape page. */
const PORTRAIT_COLUMNS = 5;

const FLAG_LABELS: Record<string, string> = { HIGH: 'High', LOW: 'Low', ABNORMAL: 'Abnormal', NORMAL: 'Normal' };
/** Letters beside a flagged value, so the flag still reads on a black-and-white printer. */
const FLAG_MARKS: Record<string, string> = { HIGH: 'H', LOW: 'L', ABNORMAL: 'A' };
const SEX_LABELS: Record<string, string> = { M: 'Male', F: 'Female', O: 'Other' };

/** Day, month name, and year, so a date never reads two ways (03/04). */
function longDate(date: string | Date): string {
  const value = typeof date === 'string' ? new Date(`${date}T00:00:00`) : date;
  return value.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

/** The reference range every result of a test was printed with, or null when they differ. */
function sharedRange(points: HealthTrendPoint[]): string | null {
  const ranges = new Set(points.map(point => (point.reference_range ?? '').trim()).filter(Boolean));
  return ranges.size === 1 ? [...ranges][0] : null;
}

function UnitMark({ point }: { point: HealthTrendPoint }) {
  if (point.unit_status === 'converted') return <sup>†</sup>;
  if (point.unit_status === 'unconverted') return <sup>‡</sup>;
  return null;
}

/**
 * Safari, and every browser on iOS, which all print with WebKit. WebKit prints a table's head only on the
 * page the table starts on (bugs.webkit.org/17205), so the repeated head cannot give its later pages a
 * margin; these browsers get real page margins instead, and their own header and footer with them.
 */
function printsWithWebKit(): boolean {
  const agent = navigator.userAgent;
  return /AppleWebKit\//.test(agent) && !/(Chrome|Chromium|Edg|OPR)\//.test(agent);
}

/**
 * The page the browser prints from Health Trends: who the results belong to, the chart, and every result
 * of each charted test with its reference range, results outside it in red. Report titles are left out,
 * since they are usually the uploaded file's name and mean nothing to whoever reads the printout.
 *
 * Hidden on screen and rendered beside the app, which print hides (index.css, "Health Trends print").
 */
const HealthTrendsPrint: React.FC<Props> = ({ trends, chartSeries, layout, scale, tables, chart, user }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wide = tables === 'combined' && trends.length > PORTRAIT_COLUMNS;
  const several = chartSeries.length > 1;
  const printLayout: TrendLayoutMode = !several ? 'overlay' : chart === 'grid' ? 'grid' : layout;
  // Sized so the header and chart share the first A4 or Letter page, ten tests included.
  const width = wide ? 1100 : 760;
  const columns = wide ? Math.min(4, chartSeries.length) : 2;
  const rows = Math.ceil(chartSeries.length / columns);
  const height =
    printLayout === 'grid'
      ? rows * 150 + (rows - 1) * 16
      : printLayout === 'stacked'
        ? chartSeries.length * (wide ? 56 : 84) + 30
        : wide ? 400 : 340;

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || chartSeries.length === 0) return;
    drawTrendChart(canvas, chartSeries, {
      layout: printLayout,
      scale,
      size: { width, height, pixelRatio: 2 },
      flagOutOfRange: true,
      valueLabels: true,
      fontScale: 1.15,
      columns,
    });
  }, [chartSeries, printLayout, scale, width, height, columns]);

  const patientName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username || '';
  const names = trends.map(item => item.name).join(', ');

  // The page title is what a browser prints in its header and offers as the PDF's file name.
  useEffect(() => {
    let previous = document.title;
    const before = () => {
      previous = document.title;
      document.title = ['Health Trends', patientName, new Date().toISOString().slice(0, 10)].filter(Boolean).join(' - ');
    };
    const after = () => {
      document.title = previous;
    };
    window.addEventListener('beforeprint', before);
    window.addEventListener('afterprint', after);
    return () => {
      window.removeEventListener('beforeprint', before);
      window.removeEventListener('afterprint', after);
    };
  }, [patientName]);

  const sorted = trends.map(item => ({
    ...item,
    points: [...(item.data?.trends ?? [])].sort((a, b) => a.date.localeCompare(b.date)),
  }));
  const dates = sorted.flatMap(item => item.points.map(point => point.date).filter(Boolean)).sort();
  const flaggedCount = sorted.reduce((sum, item) => sum + item.points.filter(point => isOutOfRange(resultFlag(point))).length, 0);
  const anyConverted = sorted.some(item => item.points.some(point => point.unit_status === 'converted'));
  const anyUnconverted = sorted.some(item => item.points.some(point => point.unit_status === 'unconverted'));
  // The legend names tests the plots do not title themselves; stacked and grid plots title every test.
  const showLegend = several && printLayout === 'overlay';

  const footnotes = (converted: boolean, unconverted: boolean, unit?: string) => (
    <>
      {converted && (
        <p className="trend-print-note">† Converted to {unit || 'the unit shown'} from the unit printed on the report.</p>
      )}
      {unconverted && <p className="trend-print-note">‡ Printed in another unit with no known conversion; not charted.</p>}
    </>
  );

  const paged = printsWithWebKit();
  const bornOn = user?.date_of_birth ? `born ${longDate(user.date_of_birth)}` : '';
  const runningLine = [patientName, bornOn].filter(Boolean).join(', ');

  // The results are one table, never one nested in another, so the browser can keep each row whole on its
  // page. Its head is repeated on every page the table continues to (except by WebKit, see above): an empty
  // row giving the page its top margin, a line naming the patient, and the column headings. The empty row
  // of its foot gives every page its bottom margin.
  const space = (span: number) => (
    <tr className="trend-print-space-row">
      <td colSpan={span}><div className="trend-print-space" /></td>
    </tr>
  );
  const head = (span: number, title: string, headings: React.ReactNode) => (
    <thead>
      {space(span)}
      <tr className="trend-print-running">
        <td colSpan={span}>
          <strong>{title}</strong>
          {runningLine && <span> · {runningLine}</span>}
        </td>
      </tr>
      <tr>{headings}</tr>
    </thead>
  );
  const foot = (span: number) => <tfoot>{space(span)}</tfoot>;
  const notes = (span: number, content: React.ReactNode) => (
    <tbody>
      <tr className="trend-print-notes">
        <td colSpan={span}>
          {content}
          <footer className="trend-print-footer">
            {flaggedCount > 0
              ? `${flaggedCount} result${flaggedCount !== 1 ? 's' : ''} outside the reference range, shown in red. `
              : 'No result is flagged outside its reference range. '}
            Each value is read against the reference range printed beside it; a result without a readable
            range keeps the flag stored for it (the lab&apos;s, or the usual adult range for that test).
          </footer>
        </td>
      </tr>
    </tbody>
  );

  const perTestTable = () => (
    <table className="trend-print-table">
      <colgroup>
        <col className="trend-print-col-date" />
        <col className="trend-print-col-result" />
        <col />
        <col className="trend-print-col-flag" />
      </colgroup>
      {head(4, 'Results by test', <><th>Date</th><th>Result</th><th>Reference range</th><th>Flag</th></>)}
      {sorted.map(item => {
        const converted = item.points.some(point => point.unit_status === 'converted');
        const unconverted = item.points.some(point => point.unit_status === 'unconverted');
        return (
          <tbody key={item.key}>
            <tr className="trend-print-section">
              <th colSpan={4} scope="rowgroup">
                <i style={{ background: item.color }} />
                {item.name}
                {item.unit && <span> · {item.unit}</span>}
              </th>
            </tr>
            {item.points.length === 0 && (
              <tr>
                <td colSpan={4} className="trend-print-empty">No results.</td>
              </tr>
            )}
            {item.points.map(point => {
              const flag = resultFlag(point);
              const flagged = isOutOfRange(flag);
              return (
                <tr key={point.result_id} className={flagged ? 'trend-print-flagged' : undefined}>
                  <td>{point.date ? longDate(point.date) : '—'}</td>
                  <td className="trend-print-value">
                    {point.value}{point.unit ? ` ${point.unit}` : ''}
                    <UnitMark point={point} />
                  </td>
                  <td>{point.reference_range || '—'}</td>
                  <td className="trend-print-flag">
                    {flag ? FLAG_LABELS[flag] ?? flag : '—'}
                  </td>
                </tr>
              );
            })}
            {(converted || unconverted) && (
              <tr className="trend-print-notes">
                <td colSpan={4}>{footnotes(converted, unconverted, item.unit)}</td>
              </tr>
            )}
          </tbody>
        );
      })}
      {notes(4, null)}
      {foot(4)}
    </table>
  );

  const combinedTable = () => {
    // A row per date, repeated when a test has more than one result that day, so no result is hidden.
    const byDate = sorted.map(item => {
      const column = new Map<string, HealthTrendPoint[]>();
      for (const point of item.points) {
        const date = point.date || '';
        column.set(date, [...(column.get(date) ?? []), point]);
      }
      return column;
    });
    const allDates = [...new Set(sorted.flatMap(item => item.points.map(point => point.date || '')))].sort();
    const tableRows = allDates.flatMap(date => {
      const count = Math.max(1, ...byDate.map(column => column.get(date)?.length ?? 0));
      return Array.from({ length: count }, (_, index) => ({ date, index }));
    });
    const ranges = sorted.map(item => sharedRange(item.points));
    const span = sorted.length + 1;

    return (
      <table className="trend-print-table trend-print-combined">
        {head(span, 'All results', (
          <>
            <th>Date</th>
            {sorted.map((item, index) => (
              <th key={item.key}>
                <span className="trend-print-column-name">
                  <i style={{ background: item.color }} />
                  {item.name}
                </span>
                {item.unit && <span className="trend-print-column-detail">{item.unit}</span>}
                {ranges[index] && <span className="trend-print-column-detail">Ref {ranges[index]}</span>}
              </th>
            ))}
          </>
        ))}
        <tbody className="trend-print-rows">
          {tableRows.map(row => (
            <tr key={`${row.date}-${row.index}`}>
              <td>{row.date ? longDate(row.date) : 'No date'}</td>
              {sorted.map((item, index) => {
                const point = byDate[index].get(row.date)?.[row.index];
                if (!point) return <td key={item.key} className="trend-print-empty">—</td>;
                const flag = resultFlag(point);
                const flagged = isOutOfRange(flag);
                // A unit differing from the column's, or a range the heading does not give, is written in.
                const ownUnit = point.unit && point.unit !== item.unit ? ` ${point.unit}` : '';
                return (
                  <td key={item.key} className={`trend-print-value${flagged ? ' trend-print-flagged-cell' : ''}`}>
                    {point.value}{ownUnit}
                    {flagged && <span className="trend-print-mark"> {FLAG_MARKS[flag]}</span>}
                    <UnitMark point={point} />
                    {!ranges[index] && point.reference_range && (
                      <span className="trend-print-cell-range">Ref {point.reference_range}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        {notes(span, (
          <>
            <p className="trend-print-note">
              H high · L low · A abnormal: each value read against the reference range printed beside it, or the
              lab&apos;s flag where there is no range to read.
            </p>
            {footnotes(anyConverted, anyUnconverted)}
          </>
        ))}
        {foot(span)}
      </table>
    );
  };

  const classes = ['trend-print', wide && 'trend-print-wide', paged && 'trend-print-paged'].filter(Boolean).join(' ');
  return createPortal(
    <div className={classes} aria-hidden>
      {/* Later in the page than index.css, so it wins over the margin of 0 there. */}
      {paged && <style>{'@media print { @page { margin: 12mm 14mm; } @page trend-print-wide { margin: 12mm 14mm; } }'}</style>}
      <header className="trend-print-header">
        <div>
          <h1>Laboratory results over time</h1>
          <p className="trend-print-tests">{names}</p>
        </div>
        <dl className="trend-print-patient">
          {patientName && <><dt>Patient</dt><dd>{patientName}</dd></>}
          {user?.date_of_birth && <><dt>Date of birth</dt><dd>{longDate(user.date_of_birth)}</dd></>}
          {user?.gender && SEX_LABELS[user.gender] && <><dt>Sex</dt><dd>{SEX_LABELS[user.gender]}</dd></>}
          {dates.length > 0 && (
            <>
              <dt>Results</dt>
              <dd>
                {dates[0] === dates[dates.length - 1]
                  ? longDate(dates[0])
                  : `${longDate(dates[0])} – ${longDate(dates[dates.length - 1])}`}
              </dd>
            </>
          )}
          <dt>Printed</dt><dd>{longDate(new Date())}</dd>
        </dl>
      </header>

      {chartSeries.length > 0 && (
        <section className="trend-print-chart">
          <canvas ref={canvasRef} />
          <div className="trend-print-legend">
            {showLegend && trends.filter(item => chartSeries.some(series => series.key === item.key)).map(item => (
              <span key={item.key}>
                <i style={{ background: item.color }} />
                {item.name}{item.unit ? ` (${item.unit})` : ''}
              </span>
            ))}
            <span>
              <i className="trend-print-flag-dot" />
              Outside reference range
            </span>
            {!showLegend && (
              <span>
                <i className="trend-print-range-swatch" />
                Reference range
              </span>
            )}
          </div>
          {showLegend && scale === 'indexed' && (
            <p className="trend-print-note">
              These tests use different units, so each line is drawn over its own range (0% its lowest
              result, 100% its highest). Compare the shapes; the tables give the real values.
            </p>
          )}
        </section>
      )}

      {tables === 'combined' ? combinedTable() : perTestTable()}
    </div>,
    document.body,
  );
};

export default HealthTrendsPrint;
