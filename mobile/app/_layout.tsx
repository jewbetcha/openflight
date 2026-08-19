import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

// Root layout. The tab navigator owns all screens; the root is a headerless
// Stack so the tabs render edge-to-edge. Connection/session state is held in the
// store and driven by the socket service, so it survives tab switches without
// any provider here.
export default function RootLayout() {
  return (
    <>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
      </Stack>
      <StatusBar style="auto" />
    </>
  );
}
