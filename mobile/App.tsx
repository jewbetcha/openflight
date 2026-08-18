import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  TouchableWithoutFeedback,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { io, type Socket } from 'socket.io-client';
import type { ConnectionState, Shot } from './types';
import { CurrentShotView } from './components/CurrentShotView';

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

export default function App() {
  const [serverUrl, setServerUrl] = useState('http://192.168.1.100:8080');
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [shots, setShots] = useState<Shot[]>([]);
  const socketRef = useRef<Socket | null>(null);

  const latestShot = shots[0] ?? null;
  const isConnected = connectionState === 'connected';

  const disconnect = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
    setConnectionState('disconnected');
  }, []);

  const connect = useCallback(() => {
    if (socketRef.current) return;

    setConnectionState('connecting');
    const socket = io(serverUrl, { transports: ['websocket', 'polling'] });
    socketRef.current = socket;

    socket.on('connect', () => {
      setConnectionState('connected');
      socket.emit('get_session');
    });

    socket.on('disconnect', () => {
      setConnectionState('disconnected');
    });

    socket.on('connect_error', () => {
      setConnectionState('error');
    });

    socket.on('session_state', (data: { shots: Shot[] }) => {
      setShots([...data.shots].reverse());
    });

    socket.on('shot', (data: { shot: Shot }) => {
      setShots((prev) => [data.shot, ...prev]);
    });
  }, [serverUrl]);

  // Close the socket if the component unmounts while connected.
  useEffect(() => {
    return () => {
      socketRef.current?.close();
    };
  }, []);

  const simulateShot = useCallback(() => {
    socketRef.current?.emit('simulate_shot');
  }, []);

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Tapping any non-interactive area dismisses the keyboard -- RN does not
          do this by default, so the URL field's keyboard would otherwise stay
          open until the return key is pressed. */}
      <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
        <View style={styles.inner}>
          <View style={styles.header}>
            <Text style={styles.title}>OpenFlight</Text>
            <View style={styles.statusPill}>
              <View style={[styles.statusDot, { backgroundColor: STATUS_COLOR[connectionState] }]} />
              <Text style={styles.statusText}>{STATUS_LABEL[connectionState]}</Text>
            </View>
          </View>

          {isConnected ? (
            <View style={styles.connectedBar}>
              <TouchableOpacity style={styles.simulateButton} onPress={simulateShot}>
                <Text style={styles.simulateButtonText}>Simulate Shot</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.disconnectButton} onPress={disconnect}>
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
                onSubmitEditing={Keyboard.dismiss}
              />
              <TouchableOpacity style={styles.connectButton} onPress={connect}>
                <Text style={styles.connectButtonText}>Connect</Text>
              </TouchableOpacity>
            </View>
          )}

          <CurrentShotView shot={latestShot} />
        </View>
      </TouchableWithoutFeedback>

      <StatusBar style="auto" />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  inner: {
    flex: 1,
  },
  container: {
    flex: 1,
    backgroundColor: '#fff',
    paddingTop: 60,
    paddingHorizontal: 16,
  },
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
