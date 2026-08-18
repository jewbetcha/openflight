import { StyleSheet, Text, View } from 'react-native';
import type { AngleQuality, SpinQuality } from '../types';

type TileVariant = 'primary' | 'secondary' | 'spin';

interface MetricTileProps {
  value: string | number;
  unit?: string;
  label: string;
  subtext?: string;
  variant?: TileVariant;
  // 'low' | 'medium' | 'high' render 1/2/3 filled dots; 'experimental' shows the
  // label only (no dots), matching the web ShotDisplay behavior.
  confidence?: AngleQuality | SpinQuality | null;
}

const FILLED_DOTS: Record<string, number> = { low: 1, medium: 2, high: 3 };

export function MetricTile({
  value,
  unit,
  label,
  subtext,
  variant = 'secondary',
  confidence,
}: MetricTileProps) {
  const filled = confidence ? (FILLED_DOTS[confidence] ?? 0) : 0;

  return (
    <View style={[styles.tile, variant === 'primary' && styles.tilePrimary]}>
      <View style={styles.valueRow}>
        <Text style={[styles.value, variant === 'primary' && styles.valuePrimary]}>{value}</Text>
        {unit ? <Text style={styles.unit}>{unit}</Text> : null}
      </View>
      <Text style={styles.label}>{label}</Text>
      {subtext ? <Text style={styles.subtext}>{subtext}</Text> : null}
      {confidence ? (
        <View style={styles.confidenceRow}>
          {filled > 0 ? (
            <View style={styles.dots}>
              {[0, 1, 2].map((i) => (
                <View key={i} style={[styles.dot, i < filled && styles.dotFilled]} />
              ))}
            </View>
          ) : null}
          <Text style={styles.confidenceLabel}>{confidence}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  tile: {
    width: '48%',
    backgroundColor: '#f6f8fa',
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#e5e9ee',
  },
  tilePrimary: {
    backgroundColor: '#eaf6ee',
    borderColor: '#bfe2cb',
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 4,
  },
  value: {
    fontSize: 26,
    fontWeight: '700',
    color: '#1a1a1a',
  },
  valuePrimary: {
    color: '#1a7f37',
  },
  unit: {
    fontSize: 13,
    color: '#666',
    fontWeight: '600',
  },
  label: {
    marginTop: 4,
    fontSize: 11,
    fontWeight: '700',
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  subtext: {
    marginTop: 2,
    fontSize: 11,
    color: '#999',
  },
  confidenceRow: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dots: {
    flexDirection: 'row',
    gap: 3,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#d0d7de',
  },
  dotFilled: {
    backgroundColor: '#1a7f37',
  },
  confidenceLabel: {
    fontSize: 10,
    color: '#999',
    textTransform: 'uppercase',
  },
});
