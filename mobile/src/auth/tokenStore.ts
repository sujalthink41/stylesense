import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * Where credentials live. The refresh token sits in the OS keystore (Android Keystore /
 * iOS Keychain); the short-lived access token stays in memory only. Web previews keep
 * everything in memory: a browser tab is not a secure store.
 */
export interface SecretStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

const memory = new Map<string, string>();

export const memoryStore: SecretStore = {
  get: async (k) => memory.get(k) ?? null,
  set: async (k, v) => {
    memory.set(k, v);
  },
  remove: async (k) => {
    memory.delete(k);
  },
};

export const deviceStore: SecretStore =
  Platform.OS === 'web'
    ? memoryStore
    : {
        get: (k) => SecureStore.getItemAsync(k),
        set: (k, v) => SecureStore.setItemAsync(k, v, { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK }),
        remove: (k) => SecureStore.deleteItemAsync(k),
      };

const REFRESH_KEY = 'stylesense.refresh_token';
const INSTALL_KEY = 'stylesense.installation_id';

export async function readRefreshToken(store: SecretStore = deviceStore): Promise<string | null> {
  return store.get(REFRESH_KEY);
}

export async function writeRefreshToken(token: string | null, store: SecretStore = deviceStore): Promise<void> {
  if (token) await store.set(REFRESH_KEY, token);
  else await store.remove(REFRESH_KEY);
}

/** One id per app install: the backend keeps exactly one session per install. */
export async function installationId(store: SecretStore = deviceStore): Promise<string> {
  const existing = await store.get(INSTALL_KEY);
  if (existing) return existing;
  const id = Crypto.randomUUID();
  await store.set(INSTALL_KEY, id);
  return id;
}
