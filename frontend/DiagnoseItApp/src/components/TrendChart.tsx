import React, { useMemo } from 'react';
import { View, StyleSheet, Dimensions } from 'react-native';
import Svg, { Line, Circle, Rect, Polyline, Text as SvgText } from 'react-native-svg';
import { tokens } from '../theme/tokens';
import {
  TrendPointInput,
  buildPlottablePoints,
  parseRefRangeSpan,
  formatAxisTick,
} from '../utils/labNumeric';

const CHART_HEIGHT = 220;
const PAD = { top: 20, right: 16, bottom: 36, left: 48 };

interface TrendChartProps {
  trends: TrendPointInput[];
}

export default function TrendChart({ trends }: TrendChartProps) {
  const width = Dimensions.get('window').width - 64;
  const chartW = width - PAD.left - PAD.right;
  const chartH = CHART_HEIGHT - PAD.top - PAD.bottom;

  const points = useMemo(() => buildPlottablePoints(trends), [trends]);

  if (points.length === 0) return null;

  const vals = points.map(p => p.val);
  let minVal = Math.min(...vals);
  let maxVal = Math.max(...vals);

  let refMin: number | null = null;
  let refMax: number | null = null;
  for (const p of points) {
    const span = parseRefRangeSpan(p.refRange);
    if (span) {
      refMin = span.min;
      refMax = span.max;
      break;
    }
  }

  if (refMin !== null && refMin < minVal) minVal = refMin;
  if (refMax !== null && refMax > maxVal) maxVal = refMax;

  const range = maxVal - minVal || 1;
  minVal -= range * 0.1;
  maxVal += range * 0.1;
  const valueSpan = maxVal - minVal || 1;

  const xScale = (i: number) => PAD.left + (i / (points.length - 1 || 1)) * chartW;
  const yScale = (v: number) => PAD.top + chartH - ((v - minVal) / valueSpan) * chartH;

  const linePoints = points.map((p, i) => `${xScale(i)},${yScale(p.val)}`).join(' ');

  const statusColor = (status: string) => {
    switch (status) {
      case 'HIGH': return tokens.coral;
      case 'LOW': return tokens.amber;
      case 'NORMAL': return tokens.sage;
      default: return tokens.teal;
    }
  };

  const gridLines = 4;

  return (
    <View style={styles.wrapper}>
      <Svg width={width} height={CHART_HEIGHT}>
        {Array.from({ length: gridLines + 1 }).map((_, i) => {
          const y = PAD.top + (i / gridLines) * chartH;
          const labelVal = maxVal - (i / gridLines) * valueSpan;
          return (
            <React.Fragment key={i}>
              <Line
                x1={PAD.left}
                y1={y}
                x2={width - PAD.right}
                y2={y}
                stroke={tokens.paperInset}
                strokeWidth={1}
              />
              <SvgText
                x={PAD.left - 6}
                y={y + 4}
                fontSize={10}
                fill={tokens.inkMuted}
                textAnchor="end"
              >
                {formatAxisTick(labelVal, valueSpan)}
              </SvgText>
            </React.Fragment>
          );
        })}

        {refMin !== null && refMax !== null && (
          <>
            <Rect
              x={PAD.left}
              y={Math.min(yScale(refMax), yScale(refMin))}
              width={chartW}
              height={Math.abs(yScale(refMin) - yScale(refMax))}
              fill="rgba(74, 124, 89, 0.12)"
            />
            <Line
              x1={PAD.left}
              y1={yScale(refMax)}
              x2={width - PAD.right}
              y2={yScale(refMax)}
              stroke="rgba(74, 124, 89, 0.4)"
              strokeWidth={1}
              strokeDasharray="4,4"
            />
            <Line
              x1={PAD.left}
              y1={yScale(refMin)}
              x2={width - PAD.right}
              y2={yScale(refMin)}
              stroke="rgba(74, 124, 89, 0.4)"
              strokeWidth={1}
              strokeDasharray="4,4"
            />
          </>
        )}

        {points.length > 1 && (
          <Polyline
            points={linePoints}
            fill="none"
            stroke={tokens.teal}
            strokeWidth={2}
          />
        )}

        {points.map((p, i) => (
          <Circle
            key={`${p.date}-${i}`}
            cx={xScale(i)}
            cy={yScale(p.val)}
            r={5}
            fill={statusColor(p.status)}
            stroke="#fff"
            strokeWidth={2}
          />
        ))}

        {points.map((p, i) => (
          <SvgText
            key={`label-${p.date}-${i}`}
            x={xScale(i)}
            y={CHART_HEIGHT - 8}
            fontSize={9}
            fill={tokens.inkMuted}
            textAnchor="middle"
          >
            {new Date(`${p.date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </SvgText>
        ))}
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginVertical: 12,
    alignItems: 'center',
  },
});
