import { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { io, type Socket } from 'socket.io-client';

// Subset of src/openflight/server.py's Shot payload -- just the fields this
// screen renders. Kept local rather than shared with ui/src/types/shot.ts
// since there's no shared package between ui/ and mobile/ yet.
interface Shot {
  timestamp: string;
  club: string;
  ball_speed_mph: number;
  club_speed_mph: number | null;
  estimated_carry_yards: number;
}

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

const STATUS_LABEL: Record<ConnectionState, string> = {
  disconnected: 'Disconnected',
  connecting: 'Connecting…',
  connected: 'Connected',
  error: 'Connection failed',
};

export default function App() {
  const [serverUrl, setServerUrl] = useState('http://192.168.1.100:8080');
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [shots, setShots] = useState<Shot[]>([]);
  const socketRef = useRef<Socket | null>(null);

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
      <Text style={styles.title}>OpenFlight</Text>

      <View style={styles.connectRow}>
        <TextInput
          style={styles.input}
          value={serverUrl}
          onChangeText={setServerUrl}
          placeholder="http://<pi-ip>:8080"
          autoCapitalize="none"
          autoCorrect={false}
          editable={connectionState !== 'connected'}
        />
        <TouchableOpacity
          style={styles.button}
          onPress={connectionState === 'connected' ? disconnect : connect}
        >
          <Text style={styles.buttonText}>
            {connectionState === 'connected' ? 'Disconnect' : 'Connect'}
          </Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.status}>{STATUS_LABEL[connectionState]}</Text>

      {connectionState === 'connected' && (
        <TouchableOpacity style={styles.simulateButton} onPress={simulateShot}>
          <Text style={styles.buttonText}>Simulate Shot</Text>
        </TouchableOpacity>
      )}

      {shots.length > 0 && (
        <View style={styles.headerRow}>
          <Text style={[styles.headerCell, styles.shotClub]}>Club</Text>
          <Text style={[styles.headerCell, styles.shotSpeed]}>Ball Speed</Text>
          <Text style={[styles.headerCell, styles.shotCarry]}>Carry</Text>
        </View>
      )}

      <FlatList
        style={styles.list}
        data={shots}
        keyExtractor={(item) => item.timestamp}
        ListEmptyComponent={<Text style={styles.empty}>No shots yet</Text>}
        renderItem={({ item }) => (
          <View style={styles.shotRow}>
            <Text style={styles.shotClub}>{item.club}</Text>
            <Text style={styles.shotSpeed}>{item.ball_speed_mph.toFixed(1)} mph</Text>
            <Text style={styles.shotCarry}>{Math.round(item.estimated_carry_yards)} yds</Text>
          </View>
        )}
      />

      <StatusBar style="auto" />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
    paddingTop: 60,
    paddingHorizontal: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    marginBottom: 16,
  },
  connectRow: {
    flexDirection: 'row',
    gap: 8,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  button: {
    backgroundColor: '#1a7f37',
    borderRadius: 8,
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  buttonText: {
    color: '#fff',
    fontWeight: '600',
  },
  status: {
    marginTop: 8,
    marginBottom: 16,
    color: '#666',
  },
  simulateButton: {
    backgroundColor: '#0969da',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
    marginBottom: 16,
  },
  list: {
    flex: 1,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingBottom: 8,
    borderBottomWidth: 2,
    borderBottomColor: '#ccc',
  },
  headerCell: {
    fontSize: 12,
    fontWeight: '700',
    color: '#666',
    textTransform: 'uppercase',
  },
  empty: {
    color: '#999',
    textAlign: 'center',
    marginTop: 32,
  },
  shotRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  shotClub: {
    flex: 1,
    fontWeight: '600',
  },
  shotSpeed: {
    flex: 1,
    textAlign: 'center',
  },
  shotCarry: {
    flex: 1,
    textAlign: 'right',
  },
});
