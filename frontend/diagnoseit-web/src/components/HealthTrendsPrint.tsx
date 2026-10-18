import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
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

/**
 * The printed page, in mm: the smaller of A4 and US Letter each way, so pages laid out here fit either paper.
 * The page has no margin of its own (index.css), so these margins are the page's padding.
 */
const PAPER = { portrait: { width: 210, height: 279.4 }, landscape: { width: 279.4, height: 210 } };
const MARGIN = { top: 12, bottom: 12, side: 14 };
/** Room left at the foot of every page, for rounding and for a browser that lays text out a little taller. */
const SLACK_MM = 5;
const PX_PER_MM = 96 / 25.4;

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
 * What the printout is made of. A block is placed whole on one page; a table's rows are placed one by one,
 * each page it reaches repeating its title and column header, so no row is ever split by a page break.
 */
type Unit =
  | { kind: 'block'; id: string; render: (measuring: boolean, pageCount: number) => React.ReactNode }
  | {
      kind: 'table';
      id: string;
      title: (continued: boolean) => React.ReactNode;
      className: string;
      head: React.ReactNode;
      rows: React.ReactNode[];
      notes: React.ReactNode;
    };

/** What one page shows of a unit: a block, some of a table's rows, or only the notes under a table. */
type Piece =
  | { kind: 'block'; id: string }
  | { kind: 'rows'; id: string; from: number; to: number; continued: boolean; notes: boolean }
  | { kind: 'notes'; id: string };

interface Measured {
  running: number;
  blocks: Record<string, number>;
  tables: Record<string, { title: number; head: number; rows: number[]; notes: number }>;
}

/** Lay the units onto pages of this content height (mm), keeping every block and every table row whole. */
function paginate(units: Unit[], measured: Measured, pageHeight: number): Piece[][] {
  const pages: Piece[][] = [[]];
  let used = 0;
  const page = () => pages[pages.length - 1];
  const newPage = () => {
    pages.push([]);
    used = measured.running;
  };

  for (const unit of units) {
    if (unit.kind === 'block') {
      const height = measured.blocks[unit.id] ?? 0;
      if (used + height > pageHeight && page().length > 0) newPage();
      page().push({ kind: 'block', id: unit.id });
      used += height;
      continue;
    }

    const size = measured.tables[unit.id];
    if (!size) continue;
    const top = size.title + size.head;
    // A table starts where its title, column header, and first row fit together.
    if (used + top + (size.rows[0] ?? 0) > pageHeight && page().length > 0) newPage();
    used += top;
    let from = 0;
    let continued = false;
    size.rows.forEach((height, index) => {
      if (used + height > pageHeight && index > from) {
        page().push({ kind: 'rows', id: unit.id, from, to: index, continued, notes: false });
        newPage();
        used += top;
        from = index;
        continued = true;
      }
      used += height;
    });
    if (used + size.notes > pageHeight) {
      page().push({ kind: 'rows', id: unit.id, from, to: size.rows.length, continued, notes: false });
      newPage();
      page().push({ kind: 'notes', id: unit.id });
    } else {
      page().push({ kind: 'rows', id: unit.id, from, to: size.rows.length, continued, notes: true });
    }
    used += size.notes;
  }
  return pages.filter(pieces => pieces.length > 0);
}

/** Height in mm of a measured element, margins included (units are flow-root, so they hold their margins). */
function heightOf(element: Element | null | undefined): number {
  return element ? element.getBoundingClientRect().height / PX_PER_MM : 0;
}

/**
 * The page the browser prints from Health Trends: who the results belong to, the chart, and every result
 * of each charted test with its reference range, results outside it in red. Report titles are left out,
 * since they are usually the uploaded file's name and mean nothing to whoever reads the printout.
 *
 * Pages are laid out here rather than left to the browser, which may cut a table row in two or drop the
 * column header after a page break: a hidden copy of every block and row is measured at the page's width,
 * and whole rows are placed onto each page under a running header naming the patient and the page.
 *
 * Hidden on screen and rendered beside the app, which print hides (index.css, "Health Trends print").
 */
const HealthTrendsPrint: React.FC<Props> = ({ trends, chartSeries, layout, scale, tables, chart, user }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<Piece[][] | null>(null);

  const wide = tables === 'combined' && trends.length > PORTRAIT_COLUMNS;
  const paper = wide ? PAPER.landscape : PAPER.portrait;
  const contentWidth = paper.width - MARGIN.side * 2;
  const contentHeight = paper.height - MARGIN.top - MARGIN.bottom - SLACK_MM;
  const several = chartSeries.length > 1;
  const printLayout: TrendLayoutMode = !several ? 'overlay' : chart === 'grid' ? 'grid' : layout;
  // Sized so the header and chart share the first page, ten tests included.
  const width = wide ? 1100 : 760;
  const columns = wide ? Math.min(4, chartSeries.length) : 2;
  const chartRows = Math.ceil(chartSeries.length / columns);
  const height =
    printLayout === 'grid'
      ? chartRows * 150 + (chartRows - 1) * 16
      : printLayout === 'stacked'
        ? chartSeries.length * (wide ? 56 : 84) + 30
        : wide ? 400 : 340;

  // The canvas is on a page, so it is drawn again whenever the pages are laid out anew.
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
  }, [chartSeries, printLayout, scale, width, height, columns, pages]);

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

  const continuedMark = (continued: boolean) => continued && <span className="trend-print-continued"> (continued)</span>;

  const runningHeader = (number: number, total: number) => (
    <div className="trend-print-running">
      <span>
        <strong>Laboratory results over time</strong>
        {patientName && ` · ${patientName}`}
        {user?.date_of_birth && ` · born ${longDate(user.date_of_birth)}`}
      </span>
      <span>Page {number} of {total}</span>
    </div>
  );

  const header = (pageCount: number) => (
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
        {pageCount > 1 && <><dt>Pages</dt><dd>{pageCount}</dd></>}
      </dl>
    </header>
  );

  const chartBlock = (measuring: boolean) => (
    <section className="trend-print-chart">
      {/* The hidden copy only needs the canvas's proportions, which its size attributes give. */}
      {measuring ? <canvas width={width * 2} height={height * 2} /> : <canvas ref={canvasRef} />}
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
  );

  const perTestUnits = (): Unit[] => sorted.map(item => {
    const converted = item.points.some(point => point.unit_status === 'converted');
    const unconverted = item.points.some(point => point.unit_status === 'unconverted');
    const title = (continued: boolean) => (
      <h2>
        <i style={{ background: item.color }} />
        {item.name}
        {item.unit && <span> · {item.unit}</span>}
        {continuedMark(continued)}
      </h2>
    );
    if (item.points.length === 0) {
      return {
        kind: 'block',
        id: `test-${item.key}`,
        render: () => <div className="trend-print-test">{title(false)}<p className="trend-print-note">No results.</p></div>,
      };
    }
    return {
      kind: 'table',
      id: `test-${item.key}`,
      title,
      className: 'trend-print-table',
      head: (
        <tr>
          <th>Date</th>
          <th>Result</th>
          <th>Reference range</th>
          <th>Flag</th>
        </tr>
      ),
      rows: item.points.map(point => {
        const flag = resultFlag(point);
        return (
          <tr key={point.result_id} className={isOutOfRange(flag) ? 'trend-print-flagged' : undefined}>
            <td>{point.date ? longDate(point.date) : '—'}</td>
            <td className="trend-print-value">
              {point.value}{point.unit ? ` ${point.unit}` : ''}
              <UnitMark point={point} />
            </td>
            <td>{point.reference_range || '—'}</td>
            <td className="trend-print-flag">{flag ? FLAG_LABELS[flag] ?? flag : '—'}</td>
          </tr>
        );
      }),
      notes: footnotes(converted, unconverted, item.unit),
    };
  });

  const combinedUnit = (): Unit => {
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

    return {
      kind: 'table',
      id: 'combined',
      title: continued => <h2>All results{continuedMark(continued)}</h2>,
      className: 'trend-print-table trend-print-combined',
      head: (
        <tr>
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
        </tr>
      ),
      rows: tableRows.map(row => (
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
      )),
      notes: (
        <>
          <p className="trend-print-note">
            H high · L low · A abnormal: each value read against the reference range printed beside it, or the
            lab&apos;s flag where there is no range to read.
          </p>
          {footnotes(anyConverted, anyUnconverted)}
        </>
      ),
    };
  };

  const units: Unit[] = [
    { kind: 'block', id: 'header', render: (_measuring, pageCount) => header(pageCount) },
    ...(chartSeries.length > 0 ? [{ kind: 'block' as const, id: 'chart', render: (measuring: boolean) => chartBlock(measuring) }] : []),
    ...(tables === 'combined' ? [combinedUnit()] : perTestUnits()),
    {
      kind: 'block',
      id: 'footer',
      render: () => (
        <footer className="trend-print-footer">
          {flaggedCount > 0
            ? `${flaggedCount} result${flaggedCount !== 1 ? 's' : ''} outside the reference range, shown in red. `
            : 'No result is flagged outside its reference range. '}
          Each value is read against the reference range printed beside it; a result without a readable
          range keeps the flag stored for it (the lab&apos;s, or the usual adult range for that test).
        </footer>
      ),
    },
  ];
  const byId = new Map(units.map(unit => [unit.id, unit]));

  // Measure the hidden copy and lay out the pages; again once web fonts have loaded, since they change sizes.
  const measure = useCallback(() => {
    const root = measureRef.current;
    if (!root) return;
    const measured: Measured = {
      running: heightOf(root.querySelector('[data-measure="running"]')),
      blocks: {},
      tables: {},
    };
    for (const element of root.querySelectorAll<HTMLElement>('[data-measure-unit]')) {
      const id = element.dataset.measureUnit!;
      if (element.dataset.kind === 'block') {
        measured.blocks[id] = heightOf(element);
      } else {
        measured.tables[id] = {
          title: heightOf(element.querySelector('[data-part="title"]')),
          head: heightOf(element.querySelector('thead')),
          rows: [...element.querySelectorAll('tbody > tr')].map(heightOf),
          notes: heightOf(element.querySelector('[data-part="notes"]')),
        };
      }
    }
    const laidOut = paginate(units, measured, contentHeight);
    setPages(current => (JSON.stringify(current) === JSON.stringify(laidOut) ? current : laidOut));
    // units is rebuilt on every render; what it is made of is in these dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trends, chartSeries, printLayout, scale, tables, user, contentHeight, width, height]);

  useLayoutEffect(() => {
    measure();
    let cancelled = false;
    document.fonts?.ready.then(() => {
      if (!cancelled) measure();
    });
    return () => {
      cancelled = true;
    };
  }, [measure]);

  const pageCount = pages?.length ?? 1;

  const renderPiece = (piece: Piece) => {
    const unit = byId.get(piece.id);
    if (!unit) return null;
    if (unit.kind === 'block') {
      return <div key={piece.id} className="trend-print-unit">{unit.render(false, pageCount)}</div>;
    }
    if (piece.kind === 'notes') {
      return <div key={`${piece.id}-notes`} className="trend-print-unit trend-print-notes">{unit.notes}</div>;
    }
    if (piece.kind !== 'rows') return null;
    return (
      <section key={`${piece.id}-${piece.from}`} className="trend-print-test">
        <div className="trend-print-unit">{unit.title(piece.continued)}</div>
        <table className={unit.className}>
          <thead>{unit.head}</thead>
          <tbody>{unit.rows.slice(piece.from, piece.to)}</tbody>
        </table>
        {piece.notes && <div className="trend-print-unit trend-print-notes">{unit.notes}</div>}
      </section>
    );
  };

  // Before the first measurement, everything is one page, which the browser breaks as it can.
  const laidOut: Piece[][] = pages ?? [units.map(unit => (
    unit.kind === 'block'
      ? { kind: 'block', id: unit.id }
      : { kind: 'rows', id: unit.id, from: 0, to: unit.rows.length, continued: false, notes: true }
  ))];

  return createPortal(
    <div className="trend-print-root" aria-hidden>
      <div className={`trend-print${wide ? ' trend-print-wide' : ''}`}>
        {laidOut.map((pieces, index) => (
          <div
            key={index}
            className="trend-print-page"
            style={{ width: `${contentWidth}mm`, paddingTop: `${MARGIN.top}mm` }}
          >
            {index > 0 && <div className="trend-print-unit">{runningHeader(index + 1, pageCount)}</div>}
            {pieces.map(renderPiece)}
          </div>
        ))}
      </div>

      {/* Laid out like a page, off screen, so every block and row can be measured. */}
      <div
        className={`trend-print trend-print-measure${wide ? ' trend-print-wide' : ''}`}
        ref={measureRef}
        style={{ width: `${contentWidth}mm` }}
      >
        <div className="trend-print-unit" data-measure="running">{runningHeader(1, 1)}</div>
        {units.map(unit => unit.kind === 'block' ? (
          <div key={unit.id} className="trend-print-unit" data-measure-unit={unit.id} data-kind="block">
            {unit.render(true, 2)}
          </div>
        ) : (
          <div key={unit.id} data-measure-unit={unit.id} data-kind="table">
            <div className="trend-print-unit" data-part="title">{unit.title(false)}</div>
            <table className={unit.className}>
              <thead>{unit.head}</thead>
              <tbody>{unit.rows}</tbody>
            </table>
            <div className="trend-print-unit trend-print-notes" data-part="notes">{unit.notes}</div>
          </div>
        ))}
      </div>
    </div>,
    document.body,
  );
};

export default HealthTrendsPrint;
