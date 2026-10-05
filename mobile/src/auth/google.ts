import Constants, { ExecutionEnvironment } from 'expo-constants';

import { ApiError } from '@/api/errors';

/** The OAuth "Web" client id: Google puts it in the ID token's audience, our API checks it. */
export const GOOGLE_WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ?? '';

/** Native Google sign-in exists in our own builds, not in Expo Go. */
export function googleSignInAvailable(): boolean {
  return Constants.executionEnvironment !== ExecutionEnvironment.StoreClient && GOOGLE_WEB_CLIENT_ID.length > 0;
}

/**
 * Shows the Google account picker and returns an ID token for our API, or null if the person
 * backed out. The module is loaded lazily so Expo Go (which lacks it) never touches it.
 */
export async function googleIdToken(): Promise<string | null> {
  const { GoogleSignin, isErrorWithCode, isSuccessResponse, statusCodes } = await import(
    '@react-native-google-signin/google-signin'
  );
  GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID, scopes: ['email', 'profile'] });
  try {
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const result = await GoogleSignin.signIn();
    if (!isSuccessResponse(result)) return null; // cancelled
    if (!result.data.idToken) throw new ApiError({ status: 0, code: 'google_failed', title: 'Google didn’t return an account' });
    return result.data.idToken;
  } catch (error) {
    if (isErrorWithCode(error) && error.code === statusCodes.IN_PROGRESS) return null;
    if (isErrorWithCode(error) && error.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
      throw new ApiError({ status: 0, code: 'google_failed', title: 'Google Play services are needed to sign in' });
    }
    throw error instanceof ApiError ? error : new ApiError({ status: 0, code: 'google_failed', title: 'Google sign-in didn’t work' });
  }
}

/** Forget the Google account choice too, so "Continue with Google" asks again after sign-out. */
export async function googleSignOut(): Promise<void> {
  if (!googleSignInAvailable()) return;
  const { GoogleSignin } = await import('@react-native-google-signin/google-signin');
  await GoogleSignin.signOut().catch(() => undefined);
}
