import type { Meta, StoryObj } from '@storybook/react';
import { AppView, type AppViewProps } from './App';
import { LaunchDaddyProvider } from './components/LaunchDaddy';
import type { Shot } from './types/shot';
import type {
  CameraStatus,
  DebugReading,
  DebugShotLog,
  RadarConfig,
} from './hooks/useSocket';

const sampleShot: Shot = {
  ball_speed_mph: 157.2,
  club_speed_mph: 103.4,
  smash_factor: 1.52,
  estimated_carry_yards: 262,
  carry_range: [254, 271],
  club: 'driver',
  timestamp: '2026-01-30T18:04:12.000Z',
  peak_magnitude: 54.3,
  launch_angle_vertical: 12.5,
  launch_angle_horizontal: -1.2,
  launch_angle_confidence: 0.78,
  spin_rpm: null,
  spin_confidence: null,
  spin_quality: null,
  carry_spin_adjusted: null,
};

const radarConfig: RadarConfig = {
  min_speed: 10,
  max_speed: 220,
  min_magnitude: 0,
  transmit_power: 0,
};

const cameraStatus: CameraStatus = {
  available: true,
  enabled: true,
  streaming: false,
  ball_detected: true,
  ball_confidence: 0.82,
};

const debugReadings: DebugReading[] = [
  {
    speed: 158.6,
    direction: 'outbound',
    magnitude: 42.1,
    timestamp: '2026-01-30T18:04:11.200Z',
  },
  {
    speed: 104.3,
    direction: 'outbound',
    magnitude: 18.7,
    timestamp: '2026-01-30T18:04:10.900Z',
  },
];

const debugShotLogs: DebugShotLog[] = [
  {
    type: 'shot',
    timestamp: '2026-01-30T18:04:12.000Z',
    radar: {
      ball_speed_mph: 157.2,
      club_speed_mph: 103.4,
      smash_factor: 1.52,
      peak_magnitude: 54.3,
    },
    camera: {
      launch_angle_vertical: 12.5,
      launch_angle_horizontal: -1.2,
      launch_angle_confidence: 0.78,
      positions_tracked: 6,
      launch_detected: true,
    },
    club: 'driver',
  },
];

const baseProps: AppViewProps = {
  connected: true,
  mockMode: true,
  debugMode: false,
  debugReadings,
  debugShotLogs,
  radarConfig,
  latestShot: sampleShot,
  shots: [
    sampleShot,
    {
      ...sampleShot,
      timestamp: '2026-01-30T18:02:02.000Z',
      ball_speed_mph: 143.9,
      club_speed_mph: 98.6,
      smash_factor: 1.46,
      estimated_carry_yards: 238,
      carry_range: [230, 246],
      launch_angle_vertical: 10.4,
      launch_angle_horizontal: 0.8,
      launch_angle_confidence: 0.63,
    },
  ],
  cameraStatus,
  clearSession: () => {},
  setClub: () => {},
  simulateShot: () => {},
  toggleDebug: () => {},
  updateRadarConfig: () => {},
  toggleCamera: () => {},
  toggleCameraStream: () => {},
};

const meta = {
  title: 'App/App',
  component: AppView,
  decorators: [
    Story => (
      <LaunchDaddyProvider>
        <Story />
      </LaunchDaddyProvider>
    ),
  ],
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof AppView>;

export default meta;

type Story = StoryObj<typeof AppView>;

export const Default: Story = {
  args: baseProps,
};

export const Disconnected: Story = {
  args: {
    ...baseProps,
    connected: false,
  },
};

const shotsViewShots: Shot[] = [
  sampleShot,
  {
    ...sampleShot,
    timestamp: '2026-01-30T18:02:02.000Z',
    ball_speed_mph: 143.9,
    club_speed_mph: 98.6,
    smash_factor: 1.46,
    estimated_carry_yards: 238,
    carry_range: [230, 246],
    launch_angle_vertical: 10.4,
    launch_angle_horizontal: 0.8,
    launch_angle_confidence: 0.63,
  },
  {
    ...sampleShot,
    timestamp: '2026-01-30T18:00:45.000Z',
    ball_speed_mph: 151.3,
    club_speed_mph: 101.8,
    smash_factor: 1.49,
    estimated_carry_yards: 252,
    carry_range: [244, 260],
    launch_angle_vertical: 11.2,
    launch_angle_horizontal: -0.4,
    launch_angle_confidence: 0.71,
  },
  {
    ...sampleShot,
    timestamp: '2026-01-30T17:58:19.000Z',
    ball_speed_mph: 149.6,
    club_speed_mph: 100.9,
    smash_factor: 1.48,
    estimated_carry_yards: 247,
    carry_range: [239, 255],
    launch_angle_vertical: 12.0,
    launch_angle_horizontal: 1.4,
    launch_angle_confidence: 0.69,
  },
  {
    ...sampleShot,
    timestamp: '2026-01-30T17:56:02.000Z',
    ball_speed_mph: 162.4,
    club_speed_mph: 105.6,
    smash_factor: 1.54,
    estimated_carry_yards: 272,
    carry_range: [264, 282],
    launch_angle_vertical: 13.1,
    launch_angle_horizontal: -0.9,
    launch_angle_confidence: 0.81,
  },
  {
    ...sampleShot,
    timestamp: '2026-01-30T17:53:37.000Z',
    ball_speed_mph: 140.2,
    club_speed_mph: 96.4,
    smash_factor: 1.45,
    estimated_carry_yards: 229,
    carry_range: [221, 236],
    launch_angle_vertical: 9.6,
    launch_angle_horizontal: 0.3,
    launch_angle_confidence: 0.58,
  },
];

export const ShotsView: Story = {
  args: {
    ...baseProps,
    initialView: 'shots',
    shots: shotsViewShots,
  },
};

export const StatsView: Story = {
  args: {
    ...baseProps,
    initialView: 'stats',
    shots: shotsViewShots,
  },
};

export const CameraView: Story = {
  args: {
    ...baseProps,
    initialView: 'camera',
  },
};

export const DebugView: Story = {
  args: {
    ...baseProps,
    initialView: 'debug',
    debugMode: true,
  },
};

export const With7IronSelected: Story = {
  args: {
    ...baseProps,
    initialClub: '7-iron',
    latestShot: {
      ...sampleShot,
      club: '7-iron',
      timestamp: '2026-01-30T18:05:20.000Z',
      ball_speed_mph: 119.8,
      club_speed_mph: 84.2,
      smash_factor: 1.42,
      estimated_carry_yards: 168,
      carry_range: [161, 175],
      launch_angle_vertical: 18.6,
      launch_angle_horizontal: 0.5,
      launch_angle_confidence: 0.72,
    },
    shots: shotsViewShots,
  },
};
