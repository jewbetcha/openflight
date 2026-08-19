# OpenFlight UI

The OpenFlight dashboard: a React + TypeScript + Vite app that connects to the
backend over `socket.io` and renders live shot data, session stats, camera ball
detection, and a screen-mounted display mode.

This README covers frontend development. For the hardware, the radar pipeline,
and how the whole system fits together, see the [root README](../README.md).

## Quick start

You need Node 20+.

### Frontend-only (recommended for UI work)

Runs Vite plus a Node Socket.IO mock on port `8080` — no Python, hardware, or
`uv` required:

```bash
npm install
npm run dev:mock
```

Open `http://localhost:5173`. Use **Simulate** to generate shots. The mock
speaks the same Socket.IO events as the real backend (`shot`, `session_state`,
club/player changes, clear/delete, stub cloud upload and shutdown).

### Against the real / Python mock backend

Start a backend without hardware from the repo root:

```bash
scripts/start-kiosk.sh --mock
```

Then in `ui/`:

```bash
npm install
npm run dev
```

See the [root README](../README.md#getting-started) for full-stack options.

The Vite server runs on port `5173`. When served there, the UI assumes the
backend is at `http://localhost:8080`. Point it elsewhere with
`VITE_SOCKET_URL`:

```bash
VITE_SOCKET_URL="http://localhost:8081" npm run dev
```

`/api/*` requests from the Vite origin are proxied to `http://localhost:8080`
(so shutdown works under `npm run dev` / `dev:mock`).

## Scripts

| Script                 | Description                                  |
| ---------------------- | -------------------------------------------- |
| `npm run dev`          | Dev server with hot reload (needs a backend) |
| `npm run dev:mock`     | Vite + Node mock backend on port 8080        |
| `npm run mock-server`  | Node mock Socket.IO server alone             |
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
- **`services/socketService.ts`** owns the connection. It receives events like
  `shot`, `session_state`, `camera_status`, `ball_detection`, and
  `trigger_status`, and sends commands like `set_club`, `clear_session`,
  `simulate_shot`, and `toggle_camera`. Read it before assuming what the
  backend emits. **`mock-server/`** implements that contract in Node for
  `npm run dev:mock`.
- **State** lives in `stores/` (Zustand: shots, system, camera, debug, …).
- **Shutdown** posts to `/api/shutdown` to stop the connected backend (stubbed
  as a no-op by the Node mock).

**Display mode** lives at `/display`: a compact, fullscreen-friendly dashboard
for mounted screens and TVs. The [root README](../README.md#tv-display-mode)
covers casting it.

**Launch Daddy** is a hidden mode toggled by a tap area in the header. When on,
new shots can fire an animated overlay.

## Project layout

A few files do most of the work. This is illustrative, not exhaustive —
components carry co-located `.css` and `.test.tsx` files.

```text
src/
  App.tsx                 # navigation, view selection, display routing
  main.tsx                # entry point
  services/socketService.ts  # socket connection, events, backend commands
  hooks/useSocket.ts      # connects on mount
  utils/serverOrigin.ts   # backend origin resolution
  stores/                 # Zustand stores (shots, system, camera, …)
  components/             # CameraFeed, ShotDisplay, StatsView, DebugPanel, …
    LaunchDaddy/          # the hidden overlay mode
mock-server/              # Node Socket.IO mock for frontend-only development
```

## Troubleshooting

**Socket won't connect.** Confirm a backend is running on port `8080` (or set
`VITE_SOCKET_URL`). For UI-only work, use `npm run dev:mock`. Connection logs
come from `services/socketService.ts`.

**Build fails.** `npm run build` surfaces TypeScript and bundling errors; `npm
run lint` catches the rest.

---

Contributing guidelines (setup, code quality, PRs) live in
[CONTRIBUTING.md](../CONTRIBUTING.md).
