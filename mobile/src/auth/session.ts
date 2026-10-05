import { create } from 'zustand';

import { ApiClient } from '@/api/client';
import { API_URL, APP_VERSION } from '@/api/config';
import { ApiError } from '@/api/errors';
import type { SignInResult, TokenPair, UserProfile } from '@/api/types';
import { GENUI_CATALOG_VERSION } from '@/genui/types.gen';

import { deviceStore, installationId, readRefreshToken, writeRefreshToken, type SecretStore } from './tokenStore';

export type AuthStatus = 'booting' | 'signedOut' | 'signedIn';

export interface SessionState {
  status: AuthStatus;
  user: UserProfile | null;
  accessToken: string | null;
  /** Restore a session from the stored refresh token (app launch). */
  boot(): Promise<void>;
  signInWithDev(email: string): Promise<void>;
  signInWithGoogle(idToken: string): Promise<void>;
  signOut(): Promise<void>;
  /** Called by the API client on 401; false means the session is over. */
  refresh(): Promise<boolean>;
}

interface Deps {
  store: SecretStore;
  baseUrl: string;
  fetchImpl?: typeof fetch;
}

/** Builds the session store; the app uses `useSession`, tests build their own. */
export function createSession(deps: Deps) {
  let api: ApiClient;
  const useStore = create<SessionState>()((set, get) => {
    const adopt = async (result: SignInResult) => {
      await writeRefreshToken(result.tokens.refresh_token, deps.store);
      set({ status: 'signedIn', user: result.user, accessToken: result.tokens.access_token });
    };
    const signedOut = async () => {
      await writeRefreshToken(null, deps.store);
      set({ status: 'signedOut', user: null, accessToken: null });
    };
    return {
      status: 'booting',
      user: null,
      accessToken: null,
      async boot() {
        const ok = await get().refresh();
        if (!ok) {
          set({ status: 'signedOut' });
          return;
        }
        try {
          const user = await api.get<UserProfile>('/v1/me');
          set({ status: 'signedIn', user });
        } catch (error) {
          // Offline at launch with a valid session: stay signed in and let screens retry.
          if (error instanceof ApiError && error.isNetwork) set({ status: 'signedIn' });
          else await signedOut();
        }
      },
      async signInWithDev(email) {
        const result = await api.post<SignInResult>(
          '/v1/auth/dev',
          { email, installation_id: await installationId(deps.store) },
          { auth: false },
        );
        await adopt(result);
      },
      async signInWithGoogle(idToken) {
        const result = await api.post<SignInResult>(
          '/v1/auth/google',
          { id_token: idToken, installation_id: await installationId(deps.store) },
          { auth: false },
        );
        await adopt(result);
      },
      async signOut() {
        const token = await readRefreshToken(deps.store);
        await signedOut();
        if (token) {
          // Best effort: the server revokes the session; we're signed out locally either way.
          await api.post('/v1/auth/logout', { refresh_token: token }, { auth: false }).catch(() => undefined);
        }
      },
      async refresh() {
        const token = await readRefreshToken(deps.store);
        if (!token) return false;
        try {
          const pair = await api.post<TokenPair>('/v1/auth/refresh', { refresh_token: token }, { auth: false });
          await writeRefreshToken(pair.refresh_token, deps.store);
          set({ accessToken: pair.access_token });
          return true;
        } catch (error) {
          if (error instanceof ApiError && error.isNetwork) return get().accessToken !== null;
          await signedOut(); // rejected or reused: the session is over
          return false;
        }
      },
    };
  });
  api = new ApiClient({
    baseUrl: deps.baseUrl,
    genuiVersion: GENUI_CATALOG_VERSION,
    appVersion: APP_VERSION,
    fetchImpl: deps.fetchImpl,
    tokens: {
      accessToken: () => useStore.getState().accessToken,
      refresh: () => useStore.getState().refresh(),
    },
  });
  return { useStore, api };
}

const app = createSession({ store: deviceStore, baseUrl: API_URL });

/** The app's session store and its authenticated API client. */
export const useSession = app.useStore;
export const api = app.api;
