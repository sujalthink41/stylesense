import { create } from 'zustand';

import type { SecretStore } from '@/auth/tokenStore';

/** unknown = not checked yet · offer = show the welcome · settled = straight to the app */
export type OnboardingStatus = 'unknown' | 'offer' | 'settled';

export interface OnboardingState {
  status: OnboardingStatus;
  /** A session the welcome started, to open once the app's screens are available. */
  next: string | null;
  check(): Promise<void>;
  /** The person answered (started Style DNA or chose later): never ask again on this phone. */
  dismiss(next?: string): Promise<void>;
  takeNext(): string | null;
  reset(): void;
}

const OFFERED_KEY = 'stylesense.onboarding_offered';

export function createOnboarding({
  store,
  fetchProfile,
  timeoutMs = 2_500,
}: {
  store: SecretStore;
  fetchProfile(): Promise<{ onboarding_done: boolean }>;
  timeoutMs?: number;
}) {
  return create<OnboardingState>()((set, get) => ({
    status: 'unknown',
    next: null,
    async check() {
      const decide = async (): Promise<OnboardingStatus> => {
        if (await store.get(OFFERED_KEY)) return 'settled';
        return (await fetchProfile()).onboarding_done ? 'settled' : 'offer';
      };
      const giveUp = new Promise<OnboardingStatus>((r) => setTimeout(() => r('settled'), timeoutMs));
      // Splash waits on this, so offline or slow simply means "skip the welcome".
      set({ status: await Promise.race([decide().catch((): OnboardingStatus => 'settled'), giveUp]) });
    },
    async dismiss(next) {
      set({ status: 'settled', next: next ?? null });
      await store.set(OFFERED_KEY, '1').catch(() => undefined);
    },
    takeNext() {
      const next = get().next;
      set({ next: null });
      return next;
    },
    reset() {
      // Sign-out: the next account on this phone gets its own welcome.
      set({ status: 'unknown', next: null });
      void store.remove(OFFERED_KEY).catch(() => undefined);
    },
  }));
}
