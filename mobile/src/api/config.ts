import Constants from 'expo-constants';

/**
 * The API base URL. Set EXPO_PUBLIC_API_URL in mobile/.env.local, e.g. your computer's LAN
 * address when running on a phone (http://192.168.1.20:8010). Defaults to the local dev stack.
 */
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8010').replace(/\/$/, '');

export const APP_VERSION = Constants.expoConfig?.version ?? '0.0.0';

/** Developer sign-in (no Google) is offered only in development builds. */
export const DEV_SIGN_IN = __DEV__ && process.env.EXPO_PUBLIC_DEV_SIGN_IN !== 'false';
