import { Keyboard, StyleSheet, TouchableWithoutFeedback, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useSessionStore } from '../../stores/useSessionStore';
import { ConnectionBar } from '../../components/ConnectionBar';
import { CurrentShotView } from '../../components/CurrentShotView';

// Live view: connection controls + the latest shot. Shots are stored
// newest-first, so index 0 is the most recent.
export default function LiveScreen() {
  const latestShot = useSessionStore((s) => s.shots[0] ?? null);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Tapping any non-interactive area dismisses the keyboard -- RN does not
          do this by default, so the URL field's keyboard would otherwise stay
          open until the return key is pressed. */}
      <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
        <View style={styles.inner}>
          <ConnectionBar />
          <CurrentShotView shot={latestShot} />
        </View>
      </TouchableWithoutFeedback>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#fff',
  },
  inner: {
    flex: 1,
    paddingHorizontal: 16,
    paddingTop: 12,
  },
});
