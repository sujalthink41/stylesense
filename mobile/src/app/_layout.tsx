import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { router, Stack } from 'expo-router';
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
import { useOnboarding } from '@/onboarding';
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
  const onboarding = useOnboarding((s) => s.status);
  const checkOnboarding = useOnboarding((s) => s.check);
  const resetOnboarding = useOnboarding((s) => s.reset);
  const next = useOnboarding((s) => s.next);

  useEffect(() => {
    void boot();
    // Force-update check: an outdated app is told so before anything else breaks.
    api
      .get<AppConfig>('/v1/app/config', { auth: false })
      .then((c) => setMustUpdate(updateState(APP_VERSION, c.min_supported_version, c.latest_version) === 'required'))
      .catch(() => undefined); // offline: never block the app on this check
  }, [boot]);

  // Signed in: decide on the welcome before the splash lifts, so the first screen doesn't jump.
  useEffect(() => {
    if (status === 'signedIn' && onboarding === 'unknown') void checkOnboarding();
    if (status === 'signedOut') resetOnboarding();
  }, [status, onboarding, checkOnboarding, resetOnboarding]);

  // The welcome started Style DNA: open it now that the app's screens exist.
  useEffect(() => {
    if (onboarding !== 'settled' || !next) return;
    const id = useOnboarding.getState().takeNext();
    if (id) router.push(`/session/${id}`);
  }, [onboarding, next]);

  const ready = fontsLoaded && status !== 'booting' && (status !== 'signedIn' || onboarding !== 'unknown');
  useEffect(() => {
    if (ready) void SplashScreen.hideAsync();
  }, [ready]);
  if (!ready) return null;

  const signedIn = status === 'signedIn';
  const welcome = signedIn && onboarding === 'offer';
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
        <Stack.Protected guard={!mustUpdate && welcome}>
          <Stack.Screen name="welcome" />
        </Stack.Protected>
        <Stack.Protected guard={!mustUpdate && signedIn && !welcome}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="session/[id]" options={{ animation: 'slide_from_right' }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}
