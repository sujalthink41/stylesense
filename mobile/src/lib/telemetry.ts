import * as Sentry from '@sentry/react-native';

import { APP_VERSION } from '@/api/config';

/**
 * Crash and error reporting through the Sentry SDK, pointed at our self-hosted GlitchTip
 * (it speaks the Sentry protocol). Off unless EXPO_PUBLIC_SENTRY_DSN is set.
 */
export function initTelemetry(): void {
  const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    release: `stylesense-mobile@${APP_VERSION}`,
    environment: __DEV__ ? 'development' : 'production',
    sendDefaultPii: false, // no IPs, no user emails
    tracesSampleRate: __DEV__ ? 1 : 0.2,
  });
}

export function reportError(error: unknown, context?: Record<string, unknown>): void {
  if (!process.env.EXPO_PUBLIC_SENTRY_DSN) return;
  Sentry.captureException(error, context ? { extra: context } : undefined);
}
