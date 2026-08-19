import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

// Bottom tab bar. Live is the fully-featured Phase 0 screen; Shots, Stats, and
// Device are placeholders that later roadmap phases fill in.
export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#1a7f37',
        tabBarInactiveTintColor: '#999',
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Live',
          tabBarIcon: ({ color, size }) => <Ionicons name="radio-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="shots"
        options={{
          title: 'Shots',
          tabBarIcon: ({ color, size }) => <Ionicons name="list-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="stats"
        options={{
          title: 'Stats',
          tabBarIcon: ({ color, size }) => <Ionicons name="stats-chart-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="device"
        options={{
          title: 'Device',
          tabBarIcon: ({ color, size }) => <Ionicons name="hardware-chip-outline" color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
