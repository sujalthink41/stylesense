import { createOnboarding } from '../store';

function memory(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    get: async (k: string) => data.get(k) ?? null,
    set: async (k: string, v: string) => void data.set(k, v),
    remove: async (k: string) => void data.delete(k),
  };
}

const profile = (done: boolean) => ({ onboarding_done: done });

describe('onboarding', () => {
  it('is offered to someone without a Style DNA who has not been asked', async () => {
    const store = createOnboarding({ store: memory(), fetchProfile: async () => profile(false) });

    await store.getState().check();

    expect(store.getState().status).toBe('offer');
  });

  it('is not offered once done, or once offered on this phone', async () => {
    const done = createOnboarding({ store: memory(), fetchProfile: async () => profile(true) });
    await done.getState().check();
    expect(done.getState().status).toBe('settled');

    const asked = createOnboarding({ store: memory({ 'stylesense.onboarding_offered': '1' }), fetchProfile: async () => profile(false) });
    await asked.getState().check();
    expect(asked.getState().status).toBe('settled');
  });

  it('answering either way remembers the offer', async () => {
    const mem = memory();
    const store = createOnboarding({ store: mem, fetchProfile: async () => profile(false) });
    await store.getState().check();

    await store.getState().dismiss();

    expect(store.getState().status).toBe('settled');
    expect(mem.data.get('stylesense.onboarding_offered')).toBe('1');
  });

  it('never blocks the app: a failed or slow check settles', async () => {
    const failing = createOnboarding({ store: memory(), fetchProfile: async () => Promise.reject(new Error('offline')) });
    await failing.getState().check();
    expect(failing.getState().status).toBe('settled');

    const slow = createOnboarding({ store: memory(), fetchProfile: () => new Promise(() => undefined), timeoutMs: 10 });
    await slow.getState().check();
    expect(slow.getState().status).toBe('settled');
  });

  it('hands over the session the welcome started, once', async () => {
    const store = createOnboarding({ store: memory(), fetchProfile: async () => profile(false) });
    await store.getState().check();

    await store.getState().dismiss('s1');

    expect(store.getState().takeNext()).toBe('s1');
    expect(store.getState().takeNext()).toBeNull();
  });

  it('reset forgets the decision (sign-out), for the next account on this phone', async () => {
    const mem = memory({ 'stylesense.onboarding_offered': '1' });
    const store = createOnboarding({ store: mem, fetchProfile: async () => profile(true) });
    await store.getState().check();

    store.getState().reset();
    await Promise.resolve();

    expect(store.getState().status).toBe('unknown');
    expect(mem.data.has('stylesense.onboarding_offered')).toBe(false);
  });
});
