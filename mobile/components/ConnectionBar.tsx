import { useEffect, useState } from 'react';
import { Keyboard, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useSessionStore } from '../stores/useSessionStore';
import { socketService } from '../services/socket';
import { DEFAULT_SERVER_URL, loadServerUrl } from '../storage/connection';
import type { ConnectionState } from '../types';

const STATUS_LABEL: Record<ConnectionState, string> = {
  disconnected: 'Disconnected',
  connecting: 'Connecting…',
  connected: 'Connected',
  error: 'Connection failed',
};

const STATUS_COLOR: Record<ConnectionState, string> = {
  disconnected: '#999',
  connecting: '#b5820a',
  connected: '#1a7f37',
  error: '#c0392b',
};

// Title bar + connection controls for the Live screen. Owns the server-URL text
// field (UI-only state, seeded from persisted storage); all connection state
// lives in the shared store and is driven by the socket service.
export function ConnectionBar() {
  const connectionState = useSessionStore((s) => s.connectionState);
  const isConnected = connectionState === 'connected';

  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER_URL);

  // Seed the field with the last-used server on mount so it doesn't have to be
  // retyped every launch.
  useEffect(() => {
    let active = true;
    loadServerUrl().then((url) => {
      if (active) setServerUrl(url);
    });
    return () => {
      active = false;
    };
  }, []);

  const connect = () => {
    Keyboard.dismiss();
    socketService.connect(serverUrl);
  };

  return (
    <View>
      <View style={styles.header}>
        <Text style={styles.title}>OpenFlight</Text>
        <View style={styles.statusPill}>
          <View style={[styles.statusDot, { backgroundColor: STATUS_COLOR[connectionState] }]} />
          <Text style={styles.statusText}>{STATUS_LABEL[connectionState]}</Text>
        </View>
      </View>

      {isConnected ? (
        <View style={styles.connectedBar}>
          <TouchableOpacity style={styles.simulateButton} onPress={() => socketService.simulateShot()}>
            <Text style={styles.simulateButtonText}>Simulate Shot</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.disconnectButton} onPress={() => socketService.disconnect()}>
            <Text style={styles.disconnectButtonText}>Disconnect</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.connectRow}>
          <TextInput
            style={styles.input}
            value={serverUrl}
            onChangeText={setServerUrl}
            placeholder="http://<pi-ip>:8080"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
            onSubmitEditing={connect}
          />
          <TouchableOpacity style={styles.connectButton} onPress={connect}>
            <Text style={styles.connectButtonText}>Connect</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1a1a1a',
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    fontSize: 12,
    color: '#666',
  },
  connectRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    marginBottom: 4,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  connectButton: {
    backgroundColor: '#1a7f37',
    borderRadius: 8,
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  connectButtonText: {
    color: '#fff',
    fontWeight: '600',
  },
  connectedBar: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    marginBottom: 4,
  },
  simulateButton: {
    flex: 1,
    backgroundColor: '#0969da',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
  },
  simulateButtonText: {
    color: '#fff',
    fontWeight: '600',
  },
  disconnectButton: {
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#ccc',
  },
  disconnectButtonText: {
    color: '#666',
    fontWeight: '600',
  },
});
