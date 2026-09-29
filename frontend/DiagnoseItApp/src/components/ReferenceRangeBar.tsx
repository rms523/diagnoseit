import React from 'react';
import { View, StyleSheet } from 'react-native';
import { tokens } from '../theme/tokens';

interface ReferenceRangeBarProps {
  width?: number | `${number}%`;
  height?: number;
}

/** Signature Specimen Ledger motif — reference-range tick marks */
export const ReferenceRangeBar: React.FC<ReferenceRangeBarProps> = ({
  width = '100%',
  height = 6,
}) => (
  <View style={[styles.wrap, { width, height }]}>
    <View style={[styles.segment, styles.low]} />
    <View style={[styles.segment, styles.normal]} />
    <View style={[styles.segment, styles.high]} />
    <View style={styles.marker} />
  </View>
);

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    borderRadius: tokens.radiusSm,
    overflow: 'hidden',
    position: 'relative',
    backgroundColor: tokens.paperInset,
  },
  segment: { flex: 1, opacity: 0.85 },
  low: { backgroundColor: tokens.amber },
  normal: { backgroundColor: tokens.sage },
  high: { backgroundColor: tokens.coral },
  marker: {
    position: 'absolute',
    left: '52%',
    top: -2,
    width: 2,
    height: 10,
    backgroundColor: tokens.teal,
    borderRadius: 1,
  },
});

export default ReferenceRangeBar;
