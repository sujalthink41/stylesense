import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { useWishlist } from '../wishlist';

jest.mock('@/auth/session', () => ({ api: { get: jest.fn(), put: jest.fn(), delete: jest.fn() } }));
const { api } = jest.requireMock('@/auth/session') as { api: Record<'get' | 'put' | 'delete', jest.Mock> };

const board = (...ids: string[]) => ({ id: 'w', name: 'Wishlist', items: ids.map((id) => ({ product: { id } })) });

async function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook = await renderHook(() => useWishlist(), { wrapper });
  await waitFor(() => expect(hook.result.current.ready).toBe(true));
  return hook;
}

beforeEach(() => jest.resetAllMocks());

describe('wishlist', () => {
  it('knows what is saved', async () => {
    api.get.mockResolvedValue(board('p1'));
    const { result } = await setup();

    expect(result.current.isSaved('p1')).toBe(true);
    expect(result.current.isSaved('p2')).toBe(false);
  });

  it('saves at once and tells the server (idempotent PUT)', async () => {
    api.get.mockResolvedValue(board());
    api.put.mockResolvedValue({ added: true });
    const { result } = await setup();

    await act(async () => result.current.toggle('p2'));

    await waitFor(() => expect(result.current.isSaved('p2')).toBe(true));
    expect(api.put).toHaveBeenCalledWith('/v1/boards/wishlist/items/p2');
  });

  it('unsaves with DELETE', async () => {
    api.get.mockResolvedValue(board('p1'));
    api.delete.mockResolvedValue(undefined);
    const { result } = await setup();

    await act(async () => result.current.toggle('p1'));

    await waitFor(() => expect(result.current.isSaved('p1')).toBe(false));
    expect(api.delete).toHaveBeenCalledWith('/v1/boards/wishlist/items/p1');
  });

  it('rolls back and reports when the server refuses', async () => {
    api.get.mockResolvedValue(board());
    api.put.mockRejectedValue(Object.assign(new Error('nope'), { code: 'board_full' }));
    const { result } = await setup();

    let ok = true;
    await act(async () => {
      ok = await result.current.toggle('p3');
    });

    expect(ok).toBe(false);
    await waitFor(() => expect(result.current.isSaved('p3')).toBe(false));
  });
});
