# Shot Visualization

How the mobile app turns a `Shot` into trajectory and dispersion graphics. All charts render with
`react-native-svg`. Both the 2D and 3D tracers now use the full RK4 flight model in
`mobile/src/utils/trajectory.ts` (drag + Magnus), falling back to the simpler parabola in
`mobile/src/utils/ballistics.ts` only when a shot has no vertical launch angle; the dispersion
charts use the `ballistics.ts` helpers.

> Most of this doc covers the **mobile app**. For the **kiosk `/scoreboard` visualizer** (the web
> trajectory + dispersion shown on a TV when no camera is streaming), see
> [Kiosk display visualizer](#kiosk-display-visualizer-web) below.

## Kiosk display visualizer (web)

On the `/scoreboard` scoreboard, when the camera is unavailable or not streaming, an animated shot
visualization for the **current club** (the latest shot's club) replaces the camera frame:

- `ui/src/components/DisplayShotVisualizer.tsx` - stacks a side-view trajectory over a top-down
  dispersion chart, filtered to the latest shot's club. On each new shot the newest arc sweeps
  left→right while its dispersion dot "slams" in as the arc lands (CSS-driven, honours
  reduce-motion and the `low-power` class).
- `ui/src/components/charts/clubCharts.tsx` - the shared `DispersionChart` (per-club 1σ ellipses,
  top-down polar) and `TrajectoryChart` (quadratic-bézier side arcs), extracted from `StatsView`
  so the Stats "Clubs" tab and the display use one source. Memoised + `React.memo` for the Pi.
- Gating lives in `Scoreboard.tsx`: the MJPEG `<img>` mounts only when the camera is live
  (`available && streaming`), and the stream URL carries the camera token (delivered to localhost
  clients only) via `ScoreboardRoute → Scoreboard`; otherwise the visualizer renders. The SVGs are
  `aria-hidden` (decorative - the numbers are in the metric grid), so screen-reader users get the
  data from the shot panel, not the charts.

## Shared ballistics helpers

`mobile/src/utils/ballistics.ts`:

- `computeApexHeight(ball_speed_mph, launch_angle_vertical, spin_rpm)` estimates apex when the
  server did not report `apex_height_yards`.
- `computeTrajectoryPoints(carry, apex)` returns the 2D arc as `{x, y}` points (x along carry, y
  height), the single source both tracers sample.
- `computeTotalDistance`, `computeFaceToPath`, `isMishit` derive secondary fields.
- `enrichShot(shot)` fills missing computed fields before the shot is persisted, so charts read
  from stored shots get the same values as live ones.

Each tracer prefers measured fields and falls back to computed ones: carry uses
`carry_spin_adjusted ?? estimated_carry_yards`, apex uses `apex_height_yards ?? computeApexHeight(...)
?? carry * 0.12`.

## ShotTracer2D

`mobile/src/components/ShotTracer2D.tsx`. A side-on arc in a padded plot box. The arc is the real
RK4 flight path (downrange × height) from `simulateTrajectory`, with the apex marker at the true
max-height sample; it falls back to the `computeTrajectoryPoints` parabola when a shot has no
vertical launch angle. Coordinate helpers map yards to pixels (`toX` over carry, `toY` over
`apex * 1.18` for headroom). The path animates on with `strokeDashoffset` (an `Animated` SVG path),
gated by reduce-motion. Distance labels respect the active distance unit.

## ShotTracer3D

`mobile/src/components/ShotTracer3D.tsx`. A perspective view with a fake camera:

- Camera constants: `CAM_Y = 8`, `CAM_Z = -35`, `FOCAL = 55`.
- `project(wx, wy, wz, W, H)` does the perspective divide (`scale = FOCAL / (wz - CAM_Z)`) and maps
  world coordinates to screen pixels.
- World axes: `x` = lateral deviation (from `launch_angle_horizontal`), `y` = height, `z` = carry
  distance. World units scale at roughly 1 unit ≈ 10 yards (`sc = 0.1`).
- Flight path: `ShotTracer3D` now integrates the real trajectory with `simulateTrajectory` in
  `mobile/src/utils/trajectory.ts` - an RK4 drag + Magnus model with spin decay that ports
  `src/openflight/ballistics.py::simulate()`. The curve includes the lateral side curve produced by
  the spin axis, not just a launch-direction drift. It projects each integrated point plus a ground
  grid, a ground shadow, and tee/apex/landing markers.
- Fallback: when a shot has no vertical launch angle, the 3D tracer reverts to the
  `computeTrajectoryPoints` parabola with a linear lateral drift
  (`carry * tan(launch_angle_horizontal)`). `ShotTracer2D` shares the same RK4 model and the same
  parabola fallback.

## DispersionChart

`mobile/src/components/DispersionChart.tsx`. A top-down landing scatter. Each shot plots at
(lateral, carry); points color by club (`CLUB_COLORS`, gold for driver, greens for woods, blue for
hybrid, amber default) and mishits are marked. An optional `selectedClub` filters the set, and the
chart draws a dispersion ellipse over the cluster.

## TrendLineChart

`mobile/src/components/TrendLineChart.tsx`. A small per-club carry trend over recent sessions, fed
by `getClubSessionTrend`. It auto-scales the y-range with 10% padding and shows an empty state under
two data points.

## ShapeBar and shot shape

`mobile/src/components/ShapeBar.tsx` renders a draw/straight/fade distribution as a single stacked
bar (green draw family, gold neutral, amber fade family). Classification lives in
`mobile/src/utils/shotShape.ts`: `classifyShotShape(face_to_path_deg, launch_angle_horizontal)`
returns one of nine shapes (straight/push/pull, draw/hook/pull-hook, fade/slice/push-slice).
`shapesFromShots` derives shapes from a shot array, using `shot.shot_shape` when present.

## Conventions

- Canvas backgrounds use the blue-tinted `C.canvas2d` / `C.canvas3d` tokens for a sky feel; the arc
  uses the gold accent.
- Every distance and speed renders through `mobile/src/utils/units.ts` so metric/imperial switches
  apply everywhere.
- Components are wrapped in `React.memo`; trajectory point arrays are memoized so re-renders on
  unrelated state stay cheap.
