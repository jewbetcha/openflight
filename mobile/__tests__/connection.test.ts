import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEFAULT_SERVER_URL, loadServerUrl, saveServerUrl } from '../storage/connection';

// Use the official in-memory mock shipped with async-storage.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

beforeEach(async () => {
  await AsyncStorage.clear();
  jest.clearAllMocks();
});

describe('connection storage', () => {
  it('returns the default URL when nothing is saved', async () => {
    await expect(loadServerUrl()).resolves.toBe(DEFAULT_SERVER_URL);
  });

  it('round-trips a saved URL', async () => {
    await saveServerUrl('http://10.0.0.5:8080');
    await expect(loadServerUrl()).resolves.toBe('http://10.0.0.5:8080');
  });

  it('falls back to the default if the read throws', async () => {
    (AsyncStorage.getItem as jest.Mock).mockRejectedValueOnce(new Error('storage unavailable'));
    await expect(loadServerUrl()).resolves.toBe(DEFAULT_SERVER_URL);
  });

  it('never throws if the write fails', async () => {
    (AsyncStorage.setItem as jest.Mock).mockRejectedValueOnce(new Error('disk full'));
    await expect(saveServerUrl('http://10.0.0.5:8080')).resolves.toBeUndefined();
  });
});
