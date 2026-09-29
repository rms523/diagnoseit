/**
 * Draws one or more test trends on a shared time axis.
 *
 * Every series is placed by the date of its report, not by its position in the list, so tests taken on
 * different days line up. Tests are rarely measured in the same unit, so overlaying them on one axis of
 * real values would be meaningless: "indexed" gives each series its own scale over the plot's full height
 * (0% its own lowest value, 100% its highest), which compares shape, while "value" keeps real numbers and
 * suits series that share a unit. Stacked panels keep real numbers too, one axis per test.
 *
 * A panel holding a single series draws it the way the single-test chart always has: the reference range
 * as a band, a gradient under the line, and each point coloured by its status.
 */

import type { HealthTrendPoint } from '../services/api';
import { formatAxisTick, parseLabNumeric, parseRefRangeSpan } from './labNumeric';

/** Series colours, in order; they read as distinct lines on the paper palette in this order. */
export const SERIES_COLORS = ['#2A7B7E', '#C45C4A', '#4A7C59', '#B8860B', '#5B6BA8', '#8E5A9B'];

const AXIS_TEXT = '#7A8094';
const GRID_LINE = 'rgba(122, 128, 148, 0.15)';
const REF_FILL = 'rgba(74, 124, 89, 0.12)';
const REF_LINE = 'rgba(74, 124, 89, 0.4)';

const STATUS_COLORS: Record<string, string> = {
  NORMAL: '#4A7C59',
  HIGH: '#C45C4A',
  LOW: '#B8860B',
  ABNORMAL: '#C45C4A',
};

export type TrendLayoutMode = 'overlay' | 'stacked';
/** 'value': one axis of real numbers. 'indexed': each series over its own range, as a percentage. */
export type TrendScaleMode = 'value' | 'indexed';

export interface TrendSeries {
  key: string;
  label: string;
  unit: string;
  color: string;
  points: HealthTrendPoint[];
}

export interface ChartPoint {
  x: number;
  y: number;
  seriesKey: string;
  label: string;
  color: string;
  trend: HealthTrendPoint;
}

export interface ChartLayout {
  width: number;
  points: ChartPoint[];
}

export interface DrawOptions {
  layout: TrendLayoutMode;
  scale: TrendScaleMode;
}

interface Plotted {
  time: number;
  value: number;
  trend: HealthTrendPoint;
}

interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** The point's date as a number, or null when the report has no date to place it on. */
function pointTime(trend: HealthTrendPoint): number | null {
  if (!trend.date) return null;
  const time = Date.parse(`${trend.date}T00:00:00`);
  return Number.isFinite(time) ? time : null;
}

/** The points of a series that can be drawn: a number for a value, and a date to place it on. */
export function plottablePoints(points: HealthTrendPoint[]): HealthTrendPoint[] {
  return points.filter(
    point =>
      point.unit_status !== 'unconverted' && parseLabNumeric(point.value) !== null && pointTime(point) !== null,
  );
}

function prepare(series: TrendSeries): Plotted[] {
  return series.points
    .map(trend => {
      const value = parseLabNumeric(trend.value);
      const time = pointTime(trend);
      if (value === null || time === null) return null;
      return { time, value, trend };
    })
    .filter((point): point is Plotted => point !== null)
    .sort((a, b) => a.time - b.time);
}

/** A span padded by a tenth at each end, so points never sit on the panel's edge. */
function paddedSpan(min: number, max: number): { min: number; max: number } {
  const range = max - min || Math.abs(max) * 0.1 || 1;
  return { min: min - range * 0.1, max: max + range * 0.1 };
}

/** The reference range shared by a series' points, when they print one. */
function referenceSpan(points: Plotted[]): { min: number; max: number } | null {
  for (const point of points) {
    const span = parseRefRangeSpan(point.trend.reference_range);
    if (span) return span;
  }
  return null;
}

export function drawTrendChart(
  canvas: HTMLCanvasElement,
  series: TrendSeries[],
  options: DrawOptions,
): ChartLayout | null {
  const wrapper = canvas.parentElement;
  if (!wrapper) return null;

  const dpr = window.devicePixelRatio || 1;
  const rect = wrapper.getBoundingClientRect();
  const W = Math.max(1, rect.width);
  const H = Math.max(1, rect.height);
  canvas.width = Math.floor(W * dpr);
  canvas.height = Math.floor(H * dpr);
  canvas.style.width = `${W}px`;
  canvas.style.height = `${H}px`;

  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const prepared = series.map(item => ({ series: item, points: prepare(item) }));
  const drawable = prepared.filter(item => item.points.length > 0);
  if (drawable.length === 0) return null;

  const PAD = { top: 24, right: 24, bottom: 44, left: 60 };
  const times = drawable.flatMap(item => item.points.map(point => point.time));
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const timeSpan = maxTime - minTime || 1;

  const chartLeft = PAD.left;
  const chartWidth = Math.max(1, W - PAD.left - PAD.right);
  const xScale = (time: number) => chartLeft + ((time - minTime) / timeSpan) * chartWidth;

  const points: ChartPoint[] = [];

  if (options.layout === 'stacked') {
    // One panel per test, each with its own axis of real values, sharing the date axis at the bottom.
    const gap = 18;
    const totalHeight = H - PAD.top - PAD.bottom;
    const panelHeight = Math.max(40, (totalHeight - gap * (drawable.length - 1)) / drawable.length);
    drawable.forEach((item, index) => {
      const panel: Rect = {
        left: chartLeft,
        top: PAD.top + index * (panelHeight + gap),
        width: chartWidth,
        height: panelHeight,
      };
      points.push(...drawPanel(ctx, panel, [item], xScale, 'value'));
    });
  } else {
    const panel: Rect = { left: chartLeft, top: PAD.top, width: chartWidth, height: Math.max(1, H - PAD.top - PAD.bottom) };
    points.push(...drawPanel(ctx, panel, drawable, xScale, options.scale));
  }

  drawDateAxis(ctx, drawable, xScale, H - PAD.bottom + 20, chartLeft, chartWidth);

  return { width: W, points };
}

/** Draws one plot area: its grid, axis labels, and every series in it. */
function drawPanel(
  ctx: CanvasRenderingContext2D,
  panel: Rect,
  entries: Array<{ series: TrendSeries; points: Plotted[] }>,
  xScale: (time: number) => number,
  scale: TrendScaleMode,
): ChartPoint[] {
  const alone = entries.length === 1;
  // Real values need one span for the whole panel; indexed gives each series its own.
  const values = entries.flatMap(entry => entry.points.map(point => point.value));
  const reference = alone ? referenceSpan(entries[0].points) : null;
  const sharedSpan = paddedSpan(
    Math.min(...values, reference ? reference.min : Infinity),
    Math.max(...values, reference ? reference.max : -Infinity),
  );

  const spans = new Map<string, { min: number; max: number }>();
  for (const entry of entries) {
    const own = entry.points.map(point => point.value);
    spans.set(
      entry.series.key,
      scale === 'indexed' && !alone ? paddedSpan(Math.min(...own), Math.max(...own)) : sharedSpan,
    );
  }

  const yFor = (key: string, value: number) => {
    const span = spans.get(key) ?? sharedSpan;
    const height = span.max - span.min || 1;
    return panel.top + panel.height - ((value - span.min) / height) * panel.height;
  };

  // Grid, with labels only when every series in the panel shares one axis.
  const gridLines = panel.height < 120 ? 3 : 5;
  const labelled = scale === 'value' || alone;
  const labelSpan = sharedSpan.max - sharedSpan.min || 1;
  ctx.strokeStyle = GRID_LINE;
  ctx.lineWidth = 1;
  ctx.font = '11px "IBM Plex Mono", monospace';
  ctx.textAlign = 'right';
  for (let i = 0; i <= gridLines; i++) {
    const y = panel.top + (i / gridLines) * panel.height;
    ctx.beginPath();
    ctx.moveTo(panel.left, y);
    ctx.lineTo(panel.left + panel.width, y);
    ctx.stroke();

    ctx.fillStyle = AXIS_TEXT;
    if (labelled) {
      ctx.fillText(formatAxisTick(sharedSpan.max - (i / gridLines) * labelSpan, labelSpan), panel.left - 8, y + 4);
    } else {
      // Every series fills the panel's height, so the axis can only speak in percentages.
      ctx.fillText(`${Math.round(100 - (i / gridLines) * 100)}%`, panel.left - 8, y + 4);
    }
  }

  if (alone && reference) {
    const y1 = yFor(entries[0].series.key, reference.max);
    const y2 = yFor(entries[0].series.key, reference.min);
    ctx.fillStyle = REF_FILL;
    ctx.fillRect(panel.left, Math.min(y1, y2), panel.width, Math.abs(y2 - y1));
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = REF_LINE;
    for (const y of [y1, y2]) {
      ctx.beginPath();
      ctx.moveTo(panel.left, y);
      ctx.lineTo(panel.left + panel.width, y);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  // The test's name on its own panel; the legend names the series when they share one.
  if (alone && entries[0].series.label) {
    ctx.fillStyle = AXIS_TEXT;
    ctx.font = '11px "IBM Plex Sans", sans-serif';
    ctx.textAlign = 'left';
    const unit = entries[0].series.unit ? ` (${entries[0].series.unit})` : '';
    ctx.fillText(`${entries[0].series.label}${unit}`, panel.left + 6, panel.top + 12);
  }

  const drawn: ChartPoint[] = [];
  for (const entry of entries) {
    const { series, points } = entry;
    const y = (value: number) => yFor(series.key, value);

    if (alone && points.length > 1) {
      // The gradient under a single line, as the single-test chart has always drawn it.
      ctx.beginPath();
      ctx.moveTo(xScale(points[0].time), y(points[0].value));
      for (const point of points.slice(1)) ctx.lineTo(xScale(point.time), y(point.value));
      ctx.lineTo(xScale(points[points.length - 1].time), panel.top + panel.height);
      ctx.lineTo(xScale(points[0].time), panel.top + panel.height);
      ctx.closePath();
      const gradient = ctx.createLinearGradient(0, panel.top, 0, panel.top + panel.height);
      gradient.addColorStop(0, 'rgba(42, 123, 126, 0.12)');
      gradient.addColorStop(1, 'rgba(42, 123, 126, 0.01)');
      ctx.fillStyle = gradient;
      ctx.fill();
    }

    if (points.length === 1) {
      // A lone point would be a line of no length, so its level is marked across the panel instead.
      ctx.strokeStyle = `${series.color}40`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(panel.left, y(points[0].value));
      ctx.lineTo(panel.left + panel.width, y(points[0].value));
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.strokeStyle = series.color;
      ctx.lineWidth = 2.5;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      points.forEach((point, index) => {
        const px = xScale(point.time);
        const py = y(point.value);
        if (index === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.stroke();
    }

    const outer = points.length === 1 ? 9 : 7;
    const inner = points.length === 1 ? 5 : 4;
    for (const point of points) {
      const px = xScale(point.time);
      const py = y(point.value);
      // On its own panel a point takes its status colour; among other tests it must stay the series' colour.
      const fill = (alone ? STATUS_COLORS[point.trend.status] : null) ?? series.color;

      ctx.beginPath();
      ctx.arc(px, py, outer, 0, Math.PI * 2);
      ctx.fillStyle = `${fill}33`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(px, py, inner, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();

      // An out-of-range result keeps a mark of its own where the dot shows which test it belongs to.
      if (!alone && STATUS_COLORS[point.trend.status] && point.trend.status !== 'NORMAL') {
        ctx.beginPath();
        ctx.arc(px, py, inner + 3, 0, Math.PI * 2);
        ctx.strokeStyle = STATUS_COLORS[point.trend.status];
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.arc(px, py, 1.5, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();

      drawn.push({
        x: px,
        y: py,
        seriesKey: series.key,
        label: series.label,
        color: series.color,
        trend: point.trend,
      });
    }
  }

  return drawn;
}

/** The dates along the bottom: up to eight, evenly spread, with the last one always shown. */
function drawDateAxis(
  ctx: CanvasRenderingContext2D,
  entries: Array<{ points: Plotted[] }>,
  xScale: (time: number) => number,
  baseline: number,
  left: number,
  width: number,
): void {
  const times = [...new Set(entries.flatMap(entry => entry.points.map(point => point.time)))].sort((a, b) => a - b);
  if (times.length === 0) return;

  ctx.fillStyle = AXIS_TEXT;
  ctx.font = '10px "IBM Plex Sans", sans-serif';
  ctx.textAlign = 'center';

  const maxLabels = Math.max(2, Math.min(8, Math.floor(width / 70)));
  const step = Math.max(1, Math.ceil(times.length / maxLabels));
  const shown = times.filter((_, index) => index % step === 0);
  if (shown[shown.length - 1] !== times[times.length - 1]) shown.push(times[times.length - 1]);

  let lastRight = left - Infinity;
  for (const time of shown) {
    const label = new Date(time).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' });
    const x = xScale(time);
    const half = ctx.measureText(label).width / 2;
    if (x - half < lastRight + 6) continue;
    ctx.fillText(label, x, baseline);
    lastRight = x + half;
  }
}
