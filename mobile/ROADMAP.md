# Mobile App Roadmap — Touchscreen-Optional, Phone-Capable-as-Sole-Interface

The goal is to bring the Expo mobile app to a sensible subset of web-UI parity, and
specifically to make it a **complete standalone interface** so a builder can skip the
kiosk touchscreen for cost/space reasons and run the Pi headless.

The mobile app stays **self-contained** in `mobile/` — no workspaces, and the `Shot`
type / socket event names are deliberately mirrored from the Python wire contract
rather than shared with `ui/`. The real source of truth is `src/openflight/server.py`'s
`shot_to_dict()` payload and its SocketIO events.

## Locked decisions

- **Scope:** Tier 1 (core golfer parity) + a foundation phase, plus the three
  sole-interface items (graceful shutdown, connection bootstrapping, device/status view).
- **Control:** **Full control** — a sole interface must do everything the touchscreen
  could. Destructive actions (**delete shot, clear session, shutdown**) are guarded by
  **confirm dialogs**; the footgun is UI-level, not a network-trust problem.
- **Navigation:** **Bottom tab bar** (Live / Shots / Stats / Device) via **expo-router**
  (the Expo SDK 54 default, file-based routing).
- **Topology:** one app works in all three setups — phone-only (headless Pi),
  phone + kiosk touchscreen, and phone + passive `/display` monitor. Same server, same app.

## Non-goals (explicitly deferred)

Camera feed, radar-config editing, trigger-diagnostic deep dive, Launch Daddy easter egg,
sim-shot badges, swing-speed mode (Tier 2), and the `/display` TV route (a web concern).
None are needed for a complete headless golfer experience; each can be added later without
rework.

---

## Phase 0 — Foundation

**Goal:** restructure so features are cheap to add. Little new user-facing behavior.

Today the app puts socket logic, connection state, and shot state inline in `App.tsx`
with `useState`. That won't scale to multiple tabs sharing session state. Mirror the web
app's proven split (a singleton socket service + a store), kept self-contained in `mobile/`.

| Work item | Detail | Files |
|---|---|---|
| Navigation shell | Bottom tabs via expo-router (Live / Shots / Stats / Device). | new `app/` (expo-router) |
| Socket service | Extract inline socket logic into a singleton mirroring `ui/src/services/socketService.ts` — one place mapping every server event → store. DRY within mobile. | `mobile/services/socket.ts` |
| State store | A store shared across tabs (zustand works in RN; or reducer + context). Holds shots, connection, session-derived flags. | `mobile/stores/` |
| Connection persistence | Persist server URL via AsyncStorage; default to AP fixed IP `192.168.4.1:8080` with `192.168.1.100` as a fallback hint; auto-reconnect with backoff. | socket service + store |
| Wire-contract expansion | Grow `types.ts` to cover later-phase events (`session_state` extras, `shot_processing`, `session_cleared`, `club_changed`, `player_changed`, `trigger_status`, `power_status`). | `mobile/types.ts` |
| Test infra | There are zero tests in `mobile/` today. Stand up `jest-expo` + `@testing-library/react-native`. Prerequisite, not optional. | `mobile/` config |

**Test story:** the socket service's event→state transitions are pure and highly testable;
cover connect/disconnect/reconnect and each event handler. **Size: M.** Risk: low, but
load-bearing.

---

## Phase 1 — Core golfer parity (Tier 1)

**Goal:** the phone is a genuinely useful launch-monitor client.

| # | Feature | Emits / consumes | Notes |
|---|---|---|---|
| 1 | Shot history list + delete | `delete_shot` → `session_cleared`/`shot` | New Shots tab. Delete behind a confirm. |
| 2 | Session stats + clear | `clear_session` → `session_cleared` | New Stats tab. Port the web aggregates. Clear behind a confirm. |
| 3 | Club selection + on-connect prompt | `set_club` / `club_changed` | Mirror the web club-select screen on first connect; reflect server-pushed club changes. |
| 4 | Player selection | `set_player` / `player_changed` | |
| 5 | Unit toggle (imperial/metric) | client-side, persisted | The gauge/tiles hardcode mph/yds today — thread a unit through `CurrentShotView`. |
| 6 | Live polish | `shot_processing` | Show capturing/calculating states + a shot-arrival flash. Makes "waiting for a shot" feel alive. |

**Test story:** unit conversion (pure, table-tested hard), stats aggregation (pure), and
reducer handling of delete/clear/club/player. Component test for club-select-on-connect.
**Size: L.** Risk: low; items are independent and land incrementally.

---

## Phase 2 — Sole-interface completeness

**Goal:** a no-touchscreen build is fully operable and diagnosable from the phone.

| # | Feature | Mechanism | Notes |
|---|---|---|---|
| 1 | Graceful shutdown | `POST /api/shutdown` (already exists) | Confirm dialog → pending/success/error, mirroring web `ShutdownDialog`. Prevents yanking power on a live Pi (SD-card corruption risk). |
| 2 | Device/Status view | `trigger_status`, `radar_config` (read-only), `power_status` | New Device tab: connection health, radar/trigger status, battery if present. The troubleshooting lifeline when there's no screen. |
| 3 | Connection bootstrapping | mDNS discovery and/or AP default | "Just tap Connect" without reading an IP off a screen you removed. |

**Test story:** shutdown state machine (confirm→pending→success/error) as a component
test; status view across present/absent hardware; discovery logic mockable. **Size: M.**
Risk: mDNS on RN can be fiddly (may need a dev-build native module, not pure Expo Go) —
ship AP-default first, treat mDNS as a stretch. Confirm the dev-build story against the
Expo SDK 54 / Expo Go constraint in `mobile/AGENTS.md` before adding native deps.

---

## Phase 3 — Deployment track (ops, parallel — not app code)

**Goal:** make the headless + AP topology real on the Pi. Independent of the app.

| Work item | Detail |
|---|---|
| Pi access-point setup | `hostapd` + `dnsmasq` setup script alongside `scripts/setup/`. Fixed AP IP the app defaults to. Optional — a builder opts in. |
| Headless start | A flag/variant of `start-kiosk.sh` that runs the server without launching Chromium (the browser step already no-ops without a display; make it intentional + documented). |

**Size: S–M.** Risk: low; fully decoupled from the mobile phases.

---

## Sequencing & dependencies

```
Phase 0 (foundation) ──► Phase 1 (parity) ──► Phase 2 (sole-interface)

Phase 3 (Pi AP + headless) ── independent, any time ──┘
```

Phase 0 gates everything. Phases 1 and 2 are each internally incremental (ship
item-by-item). Phase 3 is parallelizable.

## Cross-cutting principles

- **DRY within mobile**, but not across `ui/`↔`mobile/` — the duplicated `Shot` type and
  event names are deliberate; keep them mirrored, not shared.
- **Confirm dialogs** on all three destructive actions (delete / clear / shutdown).
- **Tests land with each feature**, not after; Phase 0 exists partly to make that possible.
- **Explicit over clever:** a plain socket-service + store, mirroring the web app's
  already-proven shape.

## Server-side contract reference

Client → server emits used by this roadmap: `get_session`, `set_club`, `set_player`,
`delete_shot`, `clear_session`, `simulate_shot`, `get_trigger_status`, `get_radar_config`;
plus `POST /api/shutdown`.

Server → client events consumed: `session_state`, `shot`, `shot_processing`,
`session_cleared`, `club_changed`, `player_changed`, `trigger_status`, `radar_config`,
`power_status`.
