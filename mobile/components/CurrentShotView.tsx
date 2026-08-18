import { ScrollView, StyleSheet, Text, View } from 'react-native';
import type { AngleQuality, Shot } from '../types';
import { MetricTile } from './MetricTile';

const BALL_SPEED_GAUGE_MAX = 200; // mph, matches the web SpeedGauge range

function getLaunchAngleQuality(confidence: number | null): AngleQuality | null {
  if (confidence === null) return null;
  if (confidence >= 0.7) return 'high';
  if (confidence >= 0.4) return 'medium';
  return 'low';
}

function formatSpinRpm(rpm: number): string {
  return Math.round(rpm).toLocaleString('en-US');
}

function signed(value: number): string {
  return (value >= 0 ? '+' : '') + value.toFixed(1);
}

export function CurrentShotView({ shot }: { shot: Shot | null }) {
  if (!shot) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyTitle}>Ready</Text>
        <Text style={styles.emptyHint}>Waiting for a shot…</Text>
      </View>
    );
  }

  const displayCarry = shot.carry_spin_adjusted ?? shot.estimated_carry_yards;
  const carrySubtext = shot.carry_spin_adjusted
    ? 'spin-adjusted'
    : `${Math.round(shot.carry_range[0])}–${Math.round(shot.carry_range[1])} yds`;

  const hasLaunch = shot.launch_angle_vertical !== null;
  const hasSpin = shot.spin_rpm !== null;
  const gaugePct = Math.min(Math.max(shot.ball_speed_mph / BALL_SPEED_GAUGE_MAX, 0), 1);

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
    >
      <View style={styles.hero}>
        <Text style={styles.heroLabel}>{shot.club}</Text>
        <View style={styles.heroValueRow}>
          <Text style={styles.heroValue}>{shot.ball_speed_mph.toFixed(1)}</Text>
          <Text style={styles.heroUnit}>mph</Text>
        </View>
        <Text style={styles.heroSublabel}>Ball Speed</Text>
        <View style={styles.gaugeTrack}>
          <View style={[styles.gaugeFill, { width: `${gaugePct * 100}%` }]} />
        </View>
      </View>

      <View style={styles.grid}>
        <MetricTile
          value={Math.round(displayCarry)}
          unit="yds"
          label="Est. Carry"
          subtext={carrySubtext}
          variant="primary"
        />
        <MetricTile
          value={shot.club_speed_mph !== null ? shot.club_speed_mph.toFixed(1) : '—'}
          unit={shot.club_speed_mph !== null ? 'mph' : undefined}
          label="Club Speed"
          subtext={shot.smash_factor !== null ? `${shot.smash_factor.toFixed(2)} smash` : undefined}
        />
        <MetricTile
          value={hasLaunch ? shot.launch_angle_vertical!.toFixed(1) : '—'}
          unit={hasLaunch ? '°' : undefined}
          label="V. Launch"
          subtext={hasLaunch ? (shot.angle_source ?? undefined) : undefined}
          confidence={hasLaunch ? getLaunchAngleQuality(shot.launch_angle_confidence) : null}
        />
        {shot.launch_angle_horizontal !== null ? (
          <MetricTile
            value={signed(shot.launch_angle_horizontal)}
            unit="°"
            label="H. Launch"
            subtext={shot.angle_source ?? undefined}
            confidence={getLaunchAngleQuality(shot.launch_angle_confidence)}
          />
        ) : null}
        {shot.club_angle_deg !== null ? (
          <MetricTile value={shot.club_angle_deg.toFixed(1)} unit="°" label="Club AoA" subtext="radar" />
        ) : null}
        {shot.club_path_deg !== null ? (
          <MetricTile value={signed(shot.club_path_deg)} unit="°" label="Club Path" subtext="radar" />
        ) : null}
        {shot.spin_axis_deg !== null ? (
          <MetricTile
            value={signed(shot.spin_axis_deg)}
            unit="°"
            label="Spin Axis"
            subtext={shot.spin_axis_deg > 2 ? 'fade' : shot.spin_axis_deg < -2 ? 'draw' : 'straight'}
          />
        ) : null}
        <MetricTile
          value={hasSpin ? formatSpinRpm(shot.spin_rpm!) : '—'}
          unit={hasSpin ? 'rpm' : undefined}
          label="Spin Rate"
          subtext={hasSpin && shot.spin_source ? (shot.spin_source === 'calculated' ? 'estimated' : 'radar') : undefined}
          variant="spin"
          confidence={hasSpin ? shot.spin_quality : null}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  content: {
    paddingBottom: 24,
  },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 64,
  },
  emptyTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#1a1a1a',
  },
  emptyHint: {
    marginTop: 6,
    fontSize: 14,
    color: '#999',
  },
  hero: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  heroLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1a7f37',
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  heroValueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
    marginTop: 4,
  },
  heroValue: {
    fontSize: 64,
    fontWeight: '800',
    color: '#1a1a1a',
  },
  heroUnit: {
    fontSize: 20,
    fontWeight: '600',
    color: '#666',
  },
  heroSublabel: {
    fontSize: 13,
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  gaugeTrack: {
    marginTop: 16,
    width: '80%',
    height: 8,
    borderRadius: 4,
    backgroundColor: '#e5e9ee',
    overflow: 'hidden',
  },
  gaugeFill: {
    height: '100%',
    borderRadius: 4,
    backgroundColor: '#1a7f37',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
});
