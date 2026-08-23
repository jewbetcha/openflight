---
icon: lucide/terminal
---

# CLI Flags

Every flag accepted by the server, grouped by subsystem.

`scripts/start-kiosk.sh` accepts most of these and forwards them. Use
`--dry-run` to print the exact command the script would run:

```bash
scripts/start-kiosk.sh --iwr6843 --dry-run
```

!!! note "Generated from the source"

    This table is derived from the argparse definitions in
    `src/openflight/server.py`. If a flag here disagrees with the code, the
    code is right — please open an issue.

## Server & web

Binding, ports, and debug output.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--mock`, `-m` | flag | Run in mock mode without radar |
| `--mock-swing-speed` | flag | Run swing speed training mode with simulated reps and no OPS radar |
| `--host` | default `0.0.0.0` | Host to bind to (default: 0.0.0.0) |
| `--web-port` | int; default `8080` | Web server port (default: 8080) |
| `--debug`, `-d` | flag | Enable verbose FFT/CFAR debug output |
| `--radar-log` | flag | Log raw radar data to console (Python logging) |
| `--show-raw` | flag | Show raw radar readings in console (signed values) |

## OPS243 radar & transport

Serial port, baud, and sample rate.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--port`, `-p` | — | Serial port for radar |
| `--ops-baud` | int | — |
| `--sample-rate` | int; default `30` | Radar sample rate in ksps (default: 30). Lower = longer buffer but lower max speed. 25=174mph/164ms, 27=187mph/152ms |

## Trigger & capture

How a capture is initiated and framed.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--trigger` | choices: `polling`, `threshold`, `speed`, `sound`; default `polling` | Trigger strategy (default: polling) |
| `--sound-pre-trigger` | int; default `16` | Pre-trigger segments S#n, 0-32 (default: 16 = 50/50 split, each segment ~4.27ms at 30ksps) |

## IWR6843 angle radar

The supported angle radar.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--iwr6843` | flag | Enable TI IWR6843 L3 capture and LCMF-v1 vertical launch angle |
| `--iwr6843-port` | — | TI serial port (auto-detect by default) |
| `--iwr6843-config` | default `config/iwr6843_l3dump_wide_24f3ms_53bin_iq16.cfg` | TI RF config matching the flashed L3 firmware |
| `--iwr6843-cal` | default `config/iwr6843_calibration_reference.json` | TI complex array/range calibration JSON |
| `--iwr6843-trigger-pin` | int; default `17` | BCM GPIO receiving the shared sound-trigger edge (default: 17) |
| `--iwr6843-tee-m` | float; default `1.575` | Antenna-center to tee slant range in metres (default: 1.575) |
| `--iwr6843-net-m` | float; default `4.6` | Antenna-center to net range in metres (default: 4.6) |
| `--iwr6843-tilt-deg` | float | Override mount tilt from the TI calibration JSON |
| `--iwr6843-radar-height-m` | float | Override antenna-center height from the TI calibration JSON |
| `--iwr6843-ball-height-m` | float; default `0.04` | Ball-center height above the floor/mat (default: 0.040) |
| `--iwr6843-tx-order` | choices: `auto`, `normal`, `reversed`; default `auto` | TI TDM chirp order; auto reads the chirp masks from the cfg |
| `--iwr6843-capture-timeout` | float; default `12.0` | Maximum seconds an OPS shot waits for its TI UART dump (default: 12) |
| `--iwr6843-output-dir` | — | Raw TI dump directory when --debug is enabled (default: <session-log-dir>/iwr6843) |
| `--iwr6843-azimuth-offset-deg` | float | Azimuth of the radar boresight relative to the target line, in degrees. Positive means boresight points right of the target line. Added to the measured club path; 0 reports club path relative to boresight. |
| `--iwr6843-horizontal-phase-reference-rad` | float | Static target-line phase measured by horizontal aim calibration. Subtracted from the TX2 horizontal proxy before angle conversion. |

## Inclinometer

LIS3DH enclosure tilt compensation.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--inclinometer` | flag | Enable LIS3DH enclosure pitch compensation for IWR6843 tilt |
| `--inclinometer-zero-offset` | float | Degrees added to raw LIS3DH pitch (default: 0) |

## Ballistics & spin

Carry model and spin handling.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--ballistics` | flag | Use the physics-based carry simulator (drag + Magnus, RK4). This is the default; shots without a vertical launch angle fall back to the legacy table estimator. |
| `--no-ballistics` | flag | Disable the physics simulator and use the legacy carry table for all shots. |
| `--calculated-spin` | flag | Replace radar-measured spin with the kinematic estimate (170*v*sin(LA)^1.2) when the launch angle was measured. The 24 GHz OPS return carries no usable spin line (see src/openflight/spin_estimate.py); the measured value is kept in spin_rpm_measured for offline scoring |

## Swing speed

Club-only training mode.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--swing-speed` | flag | Run club-only swing speed training mode (no impact or ball required) |
| `--swing-speed-threshold` | float; default `30.0` | Outbound speed threshold that starts a swing speed rep (default: 30 mph) |
| `--swing-speed-max` | float; default `130.0` | Maximum plausible swing speed accepted from OPS reports; use 0 to disable (default: 130 mph) |
| `--swing-speed-min-readings` | int; default `3` | Minimum qualifying radar readings required to count a swing speed rep (default: 3) |
| `--swing-speed-single-peak` | float; default `60.0` | Peak speed that can count as a swing from one radar reading (default: 60 mph) |
| `--swing-speed-num-reports` | int; default `8` | Number of OPS speed candidates to report per sample cycle (default: 8) |
| `--swing-speed-end-ms` | float; default `1000.0` | Milliseconds below threshold before ending a swing speed rep (default: 1000) |
| `--swing-speed-cooldown-ms` | float; default `750.0` | Cooldown after a swing speed rep before accepting another (default: 750) |
| `--swing-speed-rejected-cooldown-ms` | float; default `100.0` | Cooldown after an ignored short motion before re-arming (default: 100) |

## Logging & session data

Where session logs go and what they capture.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--session-location`, `-l` | default `range` | Location identifier for session logs (e.g., 'range', 'course', 'home') |
| `--log-dir` | — | Directory for session logs (default: ~/openflight_sessions) |
| `--no-logging` | flag | Disable session logging |

## Simulators & power

Outbound connectors and battery status.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--battery` | — | Show battery and external-power status using the selected provider |
| `--sim` | flag | Enable simulator connectors from config/sim.json (GSPro / OpenGolfSim). Off by default. |

## Camera (experimental)

Disabled in the production kiosk. See [camera & YOLO](../development/camera-yolo.md).

| Flag | Type / default | Description |
| --- | --- | --- |
| `--no-camera` | flag | Disable camera (auto-enabled if available) |
| `--camera-model` | — | Path to YOLO model for ball detection (uses Hough by default) |
| `--camera-imgsz` | int; default `256` | YOLO inference input size (256 for speed, 640 for accuracy) |
| `--hough-param2` | int; default `33` | Hough accumulator threshold (lower = more sensitive, default 33) |
| `--hough-param1` | int; default `48` | Canny edge threshold (lower = detects weaker edges, default 48) |
| `--hough-min-radius` | int; default `4` | Min ball radius in pixels (default 4) |
| `--hough-max-radius` | int; default `43` | Max ball radius in pixels (default 43) |
| `--hough-min-dist` | int; default `266` | Min distance between detected circles in pixels (default 266) |
| `--roboflow-model` | — | Roboflow model ID (e.g., 'golfballdetector/10'). Uses Roboflow API instead of Hough. |
| `--roboflow-api-key` | — | Roboflow API key (can also use ROBOFLOW_API_KEY env var) |

## K-LD7 (deprecated)

Retained for existing builds only. See [Legacy (K-LD7)](../legacy/index.md).

| Flag | Type / default | Description |
| --- | --- | --- |
| `--kld7` | flag | [DEPRECATED] Enable K-LD7 vertical angle radar (launch angle) |
| `--kld7-port` | — | K-LD7 vertical serial port (auto-detect if not specified) |
| `--kld7-angle-offset` | float; default `1.5` | K-LD7 vertical boresight offset in degrees. Not user-measurable without a corner reflector; 1.5 is the calibrated default for the standard mount (default: 1.5) |
| `--kld7-mount-tilt` | float | K-LD7 vertical radar mount tilt in degrees. REQUIRED with --kld7 — measure it with a phone inclinometer against the radar face; there is no default because a wrong tilt silently corrupts the launch angle |
| `--kld7-ball-distance` | float; default `5.0` | Radar-to-tee distance in feet (default: 5.0) |
| `--net-distance` | float; default `10.0` | Ball-to-net/screen distance in feet (two_ray). For nets beyond the ~11ft FSK range wrap, far-flight frames are de-aliased and kept instead of dropped (default: 10.0; nets at/inside the wrap are unaffected). |
| `--kld7-radar-height-inches` | float; default `4.0` | K-LD7 radar height above the ball in inches, used by the ball-speed cosine correction geometry (default: 4.0) |
| `--kld7-vertical-raw` | flag | TEST MODE: show the raw vertical launch angle for every shot the estimator produces, bypassing all display guardrails (plausibility, soft-lane, estimator-agreement, confidence floor). Default off. |
| `--kld7-horizontal` | flag | [DEPRECATED] Enable K-LD7 horizontal angle radar (club path) |
| `--kld7-horizontal-port` | — | K-LD7 horizontal serial port |
| `--kld7-horizontal-offset` | float | K-LD7 horizontal angle offset in degrees (default: 0.0) |
| `--kld7-raw-logging` | flag | Log raw K-LD7 RADC payloads (base64) in kld7_buffer session logs for offline replay and the session reviewer, without changing live angle extraction |

## K-LD7 experimental tuning (deprecated)

Off by default; for estimator work on deprecated hardware.

| Flag | Type / default | Description |
| --- | --- | --- |
| `--experimental-kld7-radc-tuning` | flag | Enable temporary K-LD7 RADC extraction tuning parameters (off by default) |
| `--experimental-kld7-speed-tolerance` | float; default `10.0` | Experimental K-LD7 RADC speed tolerance in mph (default: 10.0) |
| `--experimental-kld7-centroid-floor` | float; default `0.5` | Experimental K-LD7 RADC centroid floor fraction (default: 0.5) |
| `--experimental-kld7-spectrum-source` | choices: `f1a`, `f2a`, `f1b`, `sum12`, `sum1b`, `sumall`, `min12`, `geom12`; default `f1a` | Experimental K-LD7 spectrum used for target-bin selection (default: f1a; try sum12 for F1A+F2A non-coherent selection) |
| `--experimental-kld7-ops-bin-tol` | int; default `25` | Experimental K-LD7 RADC OPS-bin outlier tolerance (default: 25) |
| `--experimental-kld7-ops-bin-penalty` | float; default `10.0` | Experimental K-LD7 RADC OPS-bin outlier penalty (default: 10.0) |
| `--experimental-kld7-ops-anchored-min-snr` | float; default `5.0` | Experimental K-LD7 RADC OPS-anchored local peak minimum SNR (default: 5.0) |
| `--experimental-kld7-vertical-impact-energy` | float; default `3.0` | Experimental vertical K-LD7 RADC impact energy threshold (default: 3.0) |
| `--experimental-kld7-horizontal-impact-energy` | float; default `1.85` | Experimental horizontal K-LD7 RADC impact energy threshold (default: 1.85) |
| `--experimental-kld7-horizontal-retry-impact-energy` | float; default `0.5` | Experimental horizontal K-LD7 RADC retry impact energy threshold (default: 0.5) |
| `--experimental-kld7-horizontal-angle-limit` | float; default `15.0` | Experimental horizontal K-LD7 RADC angle acceptance limit in degrees (default: 15.0) |

## Wrapper-only flags

Handled by `scripts/start-kiosk.sh` itself rather than passed through.

| Flag | Description |
| --- | --- |
| `--dry-run` | Print the command that would run, then exit |
| `--trackman-test` | Enable the TrackMan comparison session workflow |
| `--mode` | **Deprecated** — rolling buffer is the only mode |
| `--buffer-split` | Buffer split point for the capture window |

## Related

- [Running & modes](../using/running.md) — the common invocations
- [Configuration files](configuration.md) — settings that are not flags
- [Constants](constants.md) — values compiled in rather than passed
