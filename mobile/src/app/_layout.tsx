import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { APP_VERSION } from '@/api/config';
import type { AppConfig } from '@/api/types';
import { api, useSession } from '@/auth/session';
import { ThemeProvider, useTheme } from '@/design/theme';
import { fontFiles } from '@/design/typography';
import { initTelemetry } from '@/lib/telemetry';
import { updateState } from '@/lib/version';

void SplashScreen.preventAutoHideAsync();
initTelemetry();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <QueryClientProvider client={queryClient}>
            <AppShell />
          </QueryClientProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

function AppShell() {
  const { colors, scheme } = useTheme();
  const [fontsLoaded] = useFonts(fontFiles);
  const status = useSession((s) => s.status);
  const boot = useSession((s) => s.boot);
  const [mustUpdate, setMustUpdate] = useState(false);

  useEffect(() => {
    void boot();
    // Force-update check: an outdated app is told so before anything else breaks.
    api
      .get<AppConfig>('/v1/app/config', { auth: false })
      .then((c) => setMustUpdate(updateState(APP_VERSION, c.min_supported_version, c.latest_version) === 'required'))
      .catch(() => undefined); // offline: never block the app on this check
  }, [boot]);

  const ready = fontsLoaded && status !== 'booting';
  useEffect(() => {
    if (ready) void SplashScreen.hideAsync();
  }, [ready]);
  if (!ready) return null;

  const signedIn = status === 'signedIn';
  return (
    <>
      <StatusBar style={scheme === 'dark' ? 'light' : 'auto'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.ground }, animation: 'fade_from_bottom' }}>
        <Stack.Protected guard={mustUpdate}>
          <Stack.Screen name="update" />
        </Stack.Protected>
        <Stack.Protected guard={!mustUpdate && !signedIn}>
          <Stack.Screen name="sign-in" />
        </Stack.Protected>
        <Stack.Protected guard={!mustUpdate && signedIn}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="session/[id]" options={{ animation: 'slide_from_right' }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}
