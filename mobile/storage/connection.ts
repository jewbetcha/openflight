import AsyncStorage from '@react-native-async-storage/async-storage';

const SERVER_URL_KEY = 'openflight.serverUrl';

// Default target for a fresh install. Today the Pi joins an existing LAN, so a
// typical private-range address is the best guess. When AP mode ships (roadmap
// Phase 3) the Pi will broadcast its own network at a fixed address and this
// default should flip to that AP IP (e.g. http://192.168.4.1:8080).
export const DEFAULT_SERVER_URL = 'http://192.168.1.100:8080';

// Load the persisted server URL, falling back to the default when nothing has
// been saved yet (or storage is unavailable). Never throws.
export async function loadServerUrl(): Promise<string> {
  try {
    const saved = await AsyncStorage.getItem(SERVER_URL_KEY);
    return saved ?? DEFAULT_SERVER_URL;
  } catch {
    return DEFAULT_SERVER_URL;
  }
}

// Persist the server URL after a successful connection so it survives restarts.
// Failures are swallowed — persistence is a convenience, not a correctness
// requirement, and must never break the connect flow.
export async function saveServerUrl(url: string): Promise<void> {
  try {
    await AsyncStorage.setItem(SERVER_URL_KEY, url);
  } catch {
    // Ignore: a failed write just means the URL isn't remembered next launch.
  }
}
