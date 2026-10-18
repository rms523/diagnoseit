/**
 * Draws one or more test trends on a shared time axis.
 *
 * Every series is placed by the date of its report, not by its position in the list, so tests taken on
 * different days line up. Tests are rarely measured in the same unit, so overlaying them on one axis of
 * real values would be meaningless: "indexed" gives each series its own scale over the plot's full height
 * (0% its own lowest value, 100% its highest), which compares shape, while "value" keeps real numbers and
 * suits series that share a unit.
 *
 * Overlaid lines turn into a tangle past three or four tests, so two layouts give each test a plot of its
 * own: "stacked" puts them in strips under one date axis, and "grid" lays small charts side by side, each
 * with its own date labels. Both keep real values and the same date range in every plot, so a dip in one
 * test lines up with the other tests on that date.
 *
 * A plot holding a single series draws it the way the single-test chart always has: the reference range
 * as a band, a fill under the line, and each point coloured by its status.
 */

import type { HealthTrendPoint } from '../services/api';
import { parseLabNumeric, parseRefRangeSpan } from './labNumeric';

/**
 * Series colours, in order; they read as distinct lines on the paper palette in this order. None is red,
 * because red marks a result outside its reference range.
 */
export const SERIES_COLORS = [
  '#2A7B7E', '#5B6BA8', '#B8860B', '#4A7C59', '#8E5A9B',
  '#8B5E3C', '#1F4E79', '#C2549A', '#5F6B7A', '#7A8B2E',
];

/** A result outside its reference range, on the printed chart and table. */
export const OUT_OF_RANGE_COLOR = '#C62828';

/** Statuses that mean the result is outside its reference range. */
export function isOutOfRange(status: string | undefined | null): boolean {
  return status === 'HIGH' || status === 'LOW' || status === 'ABNORMAL';
}

const AXIS_TEXT = '#7A8094';
const TITLE_TEXT = '#1C2333';
const VALUE_TEXT = '#4A5068';
const GRID_LINE = 'rgba(122, 128, 148, 0.15)';
const REF_FILL = 'rgba(74, 124, 89, 0.12)';
const REF_LINE = 'rgba(74, 124, 89, 0.4)';

const STATUS_COLORS: Record<string, string> = {
  NORMAL: '#4A7C59',
  HIGH: '#C45C4A',
  LOW: '#B8860B',
  ABNORMAL: '#C45C4A',
};

export type TrendLayoutMode = 'overlay' | 'stacked' | 'grid';
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
  /** Draw at this size instead of the wrapper's, for a canvas that is not on screen (the printed chart). */
  size?: { width: number; height: number; pixelRatio?: number };
  /** Every out-of-range point in red, whatever its direction, as the printed copy shows them. */
  flagOutOfRange?: boolean;
  /** Write each value beside its point, where a plot holds one test and the labels have room. */
  valueLabels?: boolean;
  /** Multiplies every text size; the printed chart is shrunk to the page, so its text is drawn larger. */
  fontScale?: number;
  /** Columns of the grid layout; by default as many as the width allows. */
  columns?: number;
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

interface Entry {
  series: TrendSeries;
  points: Plotted[];
}

/** Everything a plot needs to know about the chart around it. */
interface Frame {
  ctx: CanvasRenderingContext2D;
  xScale: (time: number) => number;
  /** Every date any series has a result on, oldest first. */
  times: number[];
  fs: number;
  flagOutOfRange: boolean;
  valueLabels: boolean;
}

/** How many charts sit side by side in the grid layout at this width. */
export function gridColumns(width: number, count: number): number {
  const fit = width >= 1100 ? 3 : width >= 620 ? 2 : 1;
  return Math.max(1, Math.min(fit, count));
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

/** A round step (1, 2, 2.5, or 5 times a power of ten) that splits the range into about `count` parts. */
function niceStep(range: number, count: number): number {
  const raw = range / Math.max(1, count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / magnitude;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * magnitude;
}

/** Decimals enough to write every multiple of the step exactly. */
function stepDecimals(step: number): number {
  let decimals = 0;
  while (decimals < 6 && Math.abs(Math.round(step * 10 ** decimals) - step * 10 ** decimals) > 1e-6) decimals++;
  return decimals;
}

interface Axis {
  min: number;
  max: number;
  ticks: number[];
  decimals: number;
}

/**
 * An axis of round numbers around the values, with a little room above and below. It never goes below zero
 * for values that cannot be negative, which an evenly padded span would do for results near zero.
 */
function niceAxis(low: number, high: number, count: number): Axis {
  if (low === high) {
    const room = Math.abs(low) * 0.1 || 1;
    low -= room;
    high += room;
  }
  const pad = (high - low) * 0.08;
  let min = low - pad;
  const max = high + pad;
  if (low >= 0 && min < 0) min = 0;
  const step = niceStep(max - min, count);
  const axis: Axis = {
    min: Math.floor(min / step + 1e-9) * step,
    max: Math.ceil(max / step - 1e-9) * step,
    ticks: [],
    decimals: stepDecimals(step),
  };
  for (let value = axis.min; value <= axis.max + step / 2; value += step) axis.ticks.push(value);
  return axis;
}

/** The reference range shared by a series' points, when they print one. */
function referenceSpan(points: Plotted[]): { min: number; max: number } | null {
  for (const point of points) {
    const span = parseRefRangeSpan(point.trend.reference_range);
    if (span) return span;
  }
  return null;
}

function font(fs: number, size: number, family: 'sans' | 'mono', weight = 400): string {
  const name = family === 'mono' ? '"IBM Plex Mono", monospace' : '"IBM Plex Sans", sans-serif';
  return `${weight} ${size * fs}px ${name}`;
}

export function drawTrendChart(
  canvas: HTMLCanvasElement,
  series: TrendSeries[],
  options: DrawOptions,
): ChartLayout | null {
  const wrapper = canvas.parentElement;
  if (!wrapper && !options.size) return null;

  const dpr = options.size?.pixelRatio ?? (window.devicePixelRatio || 1);
  const rect = options.size ?? wrapper!.getBoundingClientRect();
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

  const drawable: Entry[] = series
    .map(item => ({ series: item, points: prepare(item) }))
    .filter(item => item.points.length > 0);
  if (drawable.length === 0) return null;

  const fs = options.fontScale ?? 1;
  const times = [...new Set(drawable.flatMap(item => item.points.map(point => point.time)))].sort((a, b) => a - b);
  const minTime = times[0];
  const timeSpan = times[times.length - 1] - minTime || 1;
  const layout = drawable.length === 1 ? 'overlay' : options.layout;

  // Each plot maps the shared date range onto its own width, keeping its first and last points off the edges.
  const xScaleFor = (left: number, width: number) => {
    const inset = Math.min(14, width * 0.04);
    return (time: number) =>
      times.length === 1
        ? left + width / 2
        : left + inset + ((time - minTime) / timeSpan) * Math.max(1, width - inset * 2);
  };
  const frameFor = (left: number, width: number): Frame => ({
    ctx,
    xScale: xScaleFor(left, width),
    times,
    fs,
    flagOutOfRange: options.flagOutOfRange ?? false,
    valueLabels: options.valueLabels ?? false,
  });

  const axisWidth = 58 * fs;
  const dateAxisHeight = 26 * fs;
  // Room for a plot's title above its top axis label.
  const titleHeight = 26 * fs;
  const points: ChartPoint[] = [];

  if (layout === 'grid') {
    const columns = options.columns ?? gridColumns(W, drawable.length);
    const rows = Math.ceil(drawable.length / columns);
    const hGap = 24 * fs;
    const vGap = 14 * fs;
    const cellWidth = (W - hGap * (columns - 1)) / columns;
    const cellHeight = (H - vGap * (rows - 1)) / rows;
    drawable.forEach((entry, index) => {
      const cellLeft = (index % columns) * (cellWidth + hGap);
      const cellTop = Math.floor(index / columns) * (cellHeight + vGap);
      const panel: Rect = {
        left: cellLeft + axisWidth,
        top: cellTop + titleHeight,
        width: Math.max(1, cellWidth - axisWidth - 8 * fs),
        height: Math.max(30, cellHeight - titleHeight - dateAxisHeight),
      };
      const frame = frameFor(panel.left, panel.width);
      drawTitle(frame, entry.series, cellLeft + 4 * fs, cellTop + titleHeight - 12 * fs);
      points.push(...drawPanel(frame, panel, [entry], 'value'));
      drawDateAxis(frame, panel);
    });
  } else if (layout === 'stacked') {
    // One strip per test, each with its own axis of real values, sharing the date axis at the bottom.
    const gap = 8 * fs;
    const total = H - dateAxisHeight;
    const stripHeight = (total - gap * (drawable.length - 1)) / drawable.length;
    const left = axisWidth;
    const width = Math.max(1, W - axisWidth - 16 * fs);
    const frame = frameFor(left, width);
    let last: Rect | null = null;
    drawable.forEach((entry, index) => {
      const top = index * (stripHeight + gap);
      const panel: Rect = { left, top: top + titleHeight, width, height: Math.max(24, stripHeight - titleHeight) };
      drawTitle(frame, entry.series, 4 * fs, top + titleHeight - 12 * fs);
      points.push(...drawPanel(frame, panel, [entry], 'value'));
      last = panel;
    });
    if (last) drawDateAxis(frame, last);
  } else {
    const panel: Rect = {
      left: axisWidth,
      top: drawable.length === 1 ? titleHeight : 12 * fs,
      width: Math.max(1, W - axisWidth - 16 * fs),
      height: 0,
    };
    panel.height = Math.max(1, H - panel.top - dateAxisHeight);
    const frame = frameFor(panel.left, panel.width);
    if (drawable.length === 1) drawTitle(frame, drawable[0].series, 4 * fs, titleHeight - 12 * fs);
    points.push(...drawPanel(frame, panel, drawable, options.scale));
    drawDateAxis(frame, panel);
  }

  return { width: W, points };
}

/** A test's name over its own plot, in its series colour, with the unit beside it. */
function drawTitle(frame: Frame, series: TrendSeries, x: number, baseline: number): void {
  const { ctx, fs } = frame;
  const radius = 4 * fs;
  ctx.beginPath();
  ctx.arc(x + radius, baseline - 4 * fs, radius, 0, Math.PI * 2);
  ctx.fillStyle = series.color;
  ctx.fill();

  ctx.textAlign = 'left';
  ctx.font = font(fs, 12, 'sans', 600);
  ctx.fillStyle = TITLE_TEXT;
  const nameX = x + radius * 2 + 6 * fs;
  ctx.fillText(series.label, nameX, baseline);
  if (series.unit) {
    const nameWidth = ctx.measureText(series.label).width;
    ctx.font = font(fs, 11, 'sans');
    ctx.fillStyle = AXIS_TEXT;
    ctx.fillText(series.unit, nameX + nameWidth + 6 * fs, baseline);
  }
}

/** Draws one plot area: its grid, axis labels, and every series in it. */
function drawPanel(frame: Frame, panel: Rect, entries: Entry[], scale: TrendScaleMode): ChartPoint[] {
  const { ctx, xScale, fs } = frame;
  const alone = entries.length === 1;
  const statusColor = (status: string) =>
    frame.flagOutOfRange && isOutOfRange(status) ? OUT_OF_RANGE_COLOR : STATUS_COLORS[status];

  // Real values need one axis for the whole panel; indexed gives each series its own span.
  const values = entries.flatMap(entry => entry.points.map(point => point.value));
  const reference = alone ? referenceSpan(entries[0].points) : null;
  const tickCount = panel.height < 70 ? 2 : panel.height < 140 ? 3 : 5;
  const axis = niceAxis(
    Math.min(...values, reference ? reference.min : Infinity),
    Math.max(...values, reference ? reference.max : -Infinity),
    tickCount,
  );

  const spans = new Map<string, { min: number; max: number }>();
  for (const entry of entries) {
    if (scale === 'indexed' && !alone) {
      const own = entry.points.map(point => point.value);
      const low = Math.min(...own);
      const high = Math.max(...own);
      const pad = (high - low) * 0.1 || Math.abs(high) * 0.1 || 1;
      spans.set(entry.series.key, { min: low - pad, max: high + pad });
    } else {
      spans.set(entry.series.key, axis);
    }
  }

  const yFor = (key: string, value: number) => {
    const span = spans.get(key) ?? axis;
    const height = span.max - span.min || 1;
    return panel.top + panel.height - ((value - span.min) / height) * panel.height;
  };

  // Gridlines: one per tick across, and one per labelled date down, so a point can be read off both axes.
  ctx.strokeStyle = GRID_LINE;
  ctx.lineWidth = 1;
  ctx.font = font(fs, 11, 'mono');
  ctx.textAlign = 'right';
  ctx.fillStyle = AXIS_TEXT;
  const labelled = scale === 'value' || alone;
  if (labelled) {
    for (const tick of axis.ticks) {
      const y = yFor(entries[0].series.key, tick);
      ctx.beginPath();
      ctx.moveTo(panel.left, y);
      ctx.lineTo(panel.left + panel.width, y);
      ctx.stroke();
      ctx.fillText(tick.toFixed(axis.decimals), panel.left - 8 * fs, y + 4 * fs);
    }
  } else {
    // Every series fills the panel's height, so the axis can only speak in percentages.
    for (let i = 0; i <= 4; i++) {
      const y = panel.top + (i / 4) * panel.height;
      ctx.beginPath();
      ctx.moveTo(panel.left, y);
      ctx.lineTo(panel.left + panel.width, y);
      ctx.stroke();
      ctx.fillText(`${100 - i * 25}%`, panel.left - 8 * fs, y + 4 * fs);
    }
  }
  for (const tick of dateTicks(frame, panel)) {
    ctx.beginPath();
    ctx.moveTo(tick.x, panel.top);
    ctx.lineTo(tick.x, panel.top + panel.height);
    ctx.stroke();
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

  const drawn: ChartPoint[] = [];
  for (const entry of entries) {
    const { series, points } = entry;
    const y = (value: number) => yFor(series.key, value);

    if (alone && points.length > 1) {
      // A light fill under a single line, in the line's own colour.
      ctx.beginPath();
      ctx.moveTo(xScale(points[0].time), y(points[0].value));
      for (const point of points.slice(1)) ctx.lineTo(xScale(point.time), y(point.value));
      ctx.lineTo(xScale(points[points.length - 1].time), panel.top + panel.height);
      ctx.lineTo(xScale(points[0].time), panel.top + panel.height);
      ctx.closePath();
      const gradient = ctx.createLinearGradient(0, panel.top, 0, panel.top + panel.height);
      gradient.addColorStop(0, `${series.color}1F`);
      gradient.addColorStop(1, `${series.color}03`);
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
      ctx.lineWidth = (alone ? 2.25 : 2) * Math.min(fs, 1.3);
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

    const outer = (points.length === 1 ? 9 : 7) * Math.min(fs, 1.2);
    const inner = (points.length === 1 ? 5 : 4) * Math.min(fs, 1.2);
    const placed: ChartPoint[] = [];
    for (const point of points) {
      const px = xScale(point.time);
      const py = y(point.value);
      // On its own panel a point takes its status colour; among other tests it must stay the series' colour.
      const fill = (alone ? statusColor(point.trend.status) : null) ?? series.color;

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
        ctx.strokeStyle = statusColor(point.trend.status);
        ctx.lineWidth = frame.flagOutOfRange ? 2 : 1.5;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.arc(px, py, 1.5, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();

      placed.push({
        x: px,
        y: py,
        seriesKey: series.key,
        label: series.label,
        color: series.color,
        trend: point.trend,
      });
    }

    // Labels only where each point has room for one; in small plots they would cover the line.
    const roomy = panel.width / Math.max(1, points.length) >= 36 * fs && panel.height >= 110 * fs;
    if (alone && frame.valueLabels && roomy) drawValueLabels(frame, panel, placed, statusColor);
    drawn.push(...placed);
  }

  return drawn;
}

/**
 * Each value written over its point (under it where the point is near the top), skipping a label that
 * would overlap the one before it, so a printed chart can be read without the table.
 */
function drawValueLabels(
  frame: Frame,
  panel: Rect,
  placed: ChartPoint[],
  statusColor: (status: string) => string | undefined,
): void {
  const { ctx, fs } = frame;
  const size = 10 * fs;
  let lastRight = -Infinity;
  let lastY = 0;
  ctx.textAlign = 'center';
  for (const point of placed) {
    const flagged = isOutOfRange(point.trend.status);
    ctx.font = font(fs, 10, 'mono', flagged ? 600 : 400);
    const text = point.trend.value;
    const half = ctx.measureText(text).width / 2;
    const above = point.y - 10 * fs;
    const y = above - size < panel.top ? point.y + 10 * fs + size : above;
    // Labels at different heights can sit closer together than labels on one line.
    if (point.x - half < lastRight + 3 * fs && Math.abs(y - lastY) < size * 1.2) continue;
    ctx.fillStyle = flagged && frame.flagOutOfRange ? statusColor(point.trend.status) ?? VALUE_TEXT : VALUE_TEXT;
    ctx.fillText(text, point.x, y);
    lastRight = point.x + half;
    lastY = y;
  }
}

/**
 * Up to eight dates, evenly spread over the plot's width, the last one always included. `labelX` keeps a
 * label at the plot's edge from running off it; `x` is where the date's gridline goes.
 */
function dateTicks(frame: Frame, panel: Rect): Array<{ x: number; labelX: number; label: string }> {
  const width = panel.width;
  const { ctx, xScale, times, fs } = frame;
  ctx.save();
  ctx.font = font(fs, 10, 'sans');
  const maxLabels = Math.max(2, Math.min(8, Math.floor(width / (72 * fs))));
  const step = Math.max(1, Math.ceil(times.length / maxLabels));
  const shown = times.filter((_, index) => index % step === 0);
  if (shown[shown.length - 1] !== times[times.length - 1]) shown.push(times[times.length - 1]);

  const ticks: Array<{ x: number; labelX: number; label: string; right: number }> = [];
  for (const time of shown) {
    const label = new Date(time).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' });
    const x = xScale(time);
    const half = ctx.measureText(label).width / 2;
    const labelX = Math.min(x, panel.left + panel.width + 4 * fs - half);
    const previous = ticks[ticks.length - 1];
    if (previous && labelX - half < previous.right + 6 * fs) {
      // The last date matters most, so it replaces a neighbour it would overlap.
      if (time !== times[times.length - 1]) continue;
      ticks.pop();
    }
    ticks.push({ x, labelX, label, right: labelX + half });
  }
  ctx.restore();
  return ticks;
}

/** The dates under a plot. */
function drawDateAxis(frame: Frame, panel: Rect): void {
  const { ctx, fs } = frame;
  ctx.fillStyle = AXIS_TEXT;
  ctx.font = font(fs, 10, 'sans');
  ctx.textAlign = 'center';
  for (const tick of dateTicks(frame, panel)) {
    ctx.fillText(tick.label, tick.labelX, panel.top + panel.height + 16 * fs);
  }
}
