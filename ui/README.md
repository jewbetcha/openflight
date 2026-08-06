# OpenFlight UI

The OpenFlight dashboard: a React + TypeScript + Vite app that connects to the
backend over `socket.io` and renders live shot data, session stats, camera ball
detection, and a screen-mounted display mode.

This README covers frontend development. For the hardware, the radar pipeline,
and how the whole system fits together, see the [root README](../README.md).

## Quick start

You need Node 20+ and a running OpenFlight backend. To start a backend without
hardware, run `scripts/start-kiosk.sh --mock` from the repo root (see the
[root README](../README.md#getting-started)).

```bash
npm install
npm run dev
```

The dev server runs on port `5173`. When served there, the UI assumes the
backend is at `http://localhost:8080`. Point it elsewhere with
`VITE_SOCKET_URL`:

```bash
VITE_SOCKET_URL="http://localhost:8081" npm run dev
```

## Scripts

| Script                 | Description                                  |
| ---------------------- | -------------------------------------------- |
| `npm run dev`          | Dev server with hot reload                   |
| `npm run build`        | Type-check and build the production bundle   |
| `npm run preview`      | Serve the production build locally           |
| `npm run lint`         | ESLint                                       |
| `npm run test`         | Vitest unit tests                            |
| `npm run format`       | Format `src/` with Prettier                  |
| `npm run format:check` | Check formatting without writing             |

## How the UI connects

The app is entirely client-side. Everything flows through one socket connection.

- **`utils/serverOrigin.ts`** resolves the backend origin: `VITE_SOCKET_URL` if
  set, otherwise `http://localhost:8080` when running on the Vite dev port
  (`5173`), otherwise the page's own origin (the production case, where the
  backend serves the built UI).
- **`hooks/useSocket.ts`** owns the connection. It receives events like `shot`,
  `session_state`, `camera_status`, `ball_detection`, and `trigger_status`, and
  sends commands like `set_club`, `clear_session`, `simulate_shot`, and
  `toggle_camera`. It's the source of truth for the event contract — read it
  before assuming what the backend emits.
- **State** lives in `state/` (shot history and unit preferences) via React
  context providers.
- **Shutdown** posts to `/api/shutdown` to stop the connected backend.

**Display mode** lives at `/display`: a compact, fullscreen-friendly dashboard
for mounted screens and TVs. It always uses the dark theme for TV readability.
The [root README](../README.md#tv-display-mode) covers casting it.

**Theme** defaults to dark. Toggle light/dark from the sun/moon button in the
header; the choice is stored in `localStorage` under `openflight.theme`. Tokens
live in `src/index.css` (`:root` / `[data-theme]`).

**Launch Daddy** is a hidden mode toggled by a tap area in the header. When on,
new shots can fire an animated overlay.

## Project layout

A few files do most of the work. This is illustrative, not exhaustive —
components carry co-located `.css` and `.test.tsx` files.

```text
src/
  App.tsx                 # navigation, view selection, display routing
  main.tsx                # entry point
  hooks/useSocket.ts      # socket connection, events, backend commands
  utils/serverOrigin.ts   # backend origin resolution
  state/                  # shot history + unit preference context
  components/             # CameraFeed, ShotDisplay, StatsView, DebugPanel, …
    LaunchDaddy/          # the hidden overlay mode
```

## Troubleshooting

**Socket won't connect.** Confirm the backend is running and reachable from the
browser. If it isn't on the default port, set `VITE_SOCKET_URL`. Connection logs
come from `hooks/useSocket.ts`.

**Build fails.** `npm run build` surfaces TypeScript and bundling errors; `npm
run lint` catches the rest.

---

Contributing guidelines (setup, code quality, PRs) live in
[CONTRIBUTING.md](../CONTRIBUTING.md).
