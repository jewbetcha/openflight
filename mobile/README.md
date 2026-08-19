# OpenFlight Mobile

An [Expo](https://expo.dev/) (React Native) companion app for OpenFlight. It
connects to the OpenFlight server over Socket.IO and mirrors the web UI's live
shot data. The goal (see [ROADMAP.md](ROADMAP.md)) is a **complete standalone
interface** so a builder can run the Pi headless and skip the kiosk touchscreen.

The app is **self-contained** in `mobile/`. The `Shot` type and socket event
names are deliberately mirrored from the Python wire contract
(`src/openflight/server.py`'s `shot_to_dict()` and its SocketIO events) rather
than shared with `ui/`.

## Prerequisites

- **Node.js** — the version pinned in the repo's `.node-version` (currently
  **v24**), and npm. CI builds against this same file.
- **Expo Go on your phone** — the app targets **Expo SDK 54**. Each Expo Go
  build supports exactly one SDK version and it must match the project's, so you
  need an **SDK 54** build specifically; a newer Expo Go rejects the app with
  *"Project is incompatible with this version of Expo Go."* Getting the right
  build differs by platform — see [Get an SDK 54 Expo Go](#get-an-sdk-54-expo-go).
  **Do not upgrade the Expo SDK** without confirming the Expo Go / dev-build
  story first — the SDK is pinned to match the maintainer's Expo Go (see
  [AGENTS.md](AGENTS.md)).
- **A running OpenFlight server** to connect to (see
  [Connecting to the server](#connecting-to-the-server)).
- Your **phone and computer on the same Wi-Fi / LAN**.

## Install (first time only)

```bash
cd mobile
npm install
```

## Run the dev server

Once dependencies are installed, from the repo root:

```bash
make mobile-dev
```

or directly:

```bash
cd mobile && npx expo start   # equivalently: npm start
```

Both just start Metro (they don't reinstall). This launches the bundler and
prints a **QR code** in the terminal.

## Testing on a phone with Expo Go

### Get an SDK 54 Expo Go

Each Expo Go build supports exactly one SDK version. The App Store / Play Store
only ever offer the **latest** build, so where you get an SDK 54 build depends
on your platform:

| Target | How to get an SDK 54 Expo Go |
| --- | --- |
| **iPhone (physical)** | The App Store Expo Go is currently capped at **SDK 54** (SDK 55+ is stuck in Apple review), so it already matches. Physical iPhones can't sideload other versions. |
| **Android (device or emulator)** | The Play Store serves the latest (~SDK 57), which **won't** run the app, and it has no version picker. Sideload the SDK 54 build instead — see below. |
| **iOS Simulator** | Download the SDK 54 build from [expo.dev/go](https://expo.dev/go). |

On **Android**, get the SDK 54 build one of two ways:

```sh
npx expo-go download android 54   # downloads the SDK 54 Expo Go, cached in ~/.expo
```

or pick **SDK 54** + your target at [expo.dev/go](https://expo.dev/go) and
install the APK (you'll enable "install unknown apps"). The sideloaded build
replaces the Play Store Expo Go — one Expo Go SDK per device at a time.

> For anything beyond quick local testing, use a
> [development build](https://docs.expo.dev/develop/development-builds/introduction/)
> instead: a binary compiled for our exact SDK, independent of whatever Expo Go
> version the stores ship.

### Run it

1. Install an **SDK 54** Expo Go (see above).
2. Make sure your **phone and dev machine are on the same Wi-Fi network**.
3. Start the dev server: `make mobile-dev`.
4. Scan the QR code:
   - **iOS** — open the built-in **Camera** app and point it at the QR; tap the
     Expo banner.
   - **Android** — open **Expo Go** and use its **Scan QR code** option.
5. The app downloads the JS bundle from Metro and opens on your phone. Saving a
   file hot-reloads it.

### If the QR / LAN connection fails

Some networks (guest Wi-Fi, corporate APs with client isolation) block the
phone from reaching Metro on your machine. Use a tunnel instead:

```bash
cd mobile && npx expo start --tunnel
```

Tunnel mode routes through Expo's servers (slower, needs `@expo/ngrok`) but
works across network boundaries.

### After changing `babel.config.js` or the entry point

Metro caches aggressively. Clear it so changes take effect:

```bash
cd mobile && npx expo start -c
```

### Simulator / emulator (optional)

If you have Xcode or Android Studio set up, you can skip the phone:

```bash
npm run ios       # iOS Simulator
npm run android   # Android emulator
```

## Connecting to the server

The app talks to the OpenFlight Python server's Socket.IO endpoint on **port
8080**.

1. Start a server for the app to reach. For development without hardware, run
   the mock server from the repo root:

   ```bash
   make dev        # scripts/start-kiosk.sh --mock
   ```

   Or run the real server on the Pi (`make start`).

2. Find the server machine's LAN IP:

   ```bash
   ipconfig getifaddr en0   # macOS
   hostname -I              # Linux / Raspberry Pi
   ```

3. In the app's connection screen, enter `http://<server-ip>:8080` (e.g.
   `http://192.168.1.100:8080`). A successful connection is remembered for next
   launch. The default guess is `http://192.168.1.100:8080` — change it to your
   server's address.

The phone and the server must be on the same LAN. There is a **Simulate**
action to generate a fake shot end-to-end once connected.

## Tests

```bash
npm test          # Jest (jest-expo)
npm run test:watch
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "Project is incompatible with this version of Expo Go" | Your Expo Go isn't SDK 54. Install an SDK 54 build (see [Get an SDK 54 Expo Go](#get-an-sdk-54-expo-go)); don't bump the SDK (see [AGENTS.md](AGENTS.md)). |
| App loads but can't connect to the server | Confirm phone + server share the LAN, the server is running on port 8080, the IP is correct, and no firewall blocks 8080. |
| QR scan does nothing / times out | Use `npx expo start --tunnel`. |
| Stale code after editing babel/entry config | `npx expo start -c` to clear the Metro cache. |
