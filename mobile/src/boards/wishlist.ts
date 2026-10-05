import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import type { BoardView } from '@/api/types';
import { api } from '@/auth/session';

export const WISHLIST_KEY = ['board', 'wishlist'] as const;

type Saved = Pick<BoardView, 'id' | 'name'> & { items: { product: { id: string } }[] };

/**
 * The heart: flips at once, then tells the server. Both writes are idempotent (PUT/DELETE on
 * the item), so a retry or a double tap can't duplicate; a refusal flips it back.
 */
export function useWishlist() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: WISHLIST_KEY, queryFn: () => api.get<Saved>('/v1/boards/wishlist') });

  const isSaved = useCallback((productId: string) => !!query.data?.items.some((i) => i.product.id === productId), [query.data]);

  const toggle = useCallback(
    async (productId: string): Promise<boolean> => {
      const before = client.getQueryData<Saved>(WISHLIST_KEY);
      if (!before) return false;
      const saving = !before.items.some((i) => i.product.id === productId);
      client.setQueryData<Saved>(WISHLIST_KEY, {
        ...before,
        items: saving ? [{ product: { id: productId } }, ...before.items] : before.items.filter((i) => i.product.id !== productId),
      });
      try {
        const path = `/v1/boards/wishlist/items/${productId}`;
        await (saving ? api.put(path) : api.delete(path));
        void client.invalidateQueries({ queryKey: ['boards'] }); // the Saved tab's counts
        return true;
      } catch {
        client.setQueryData(WISHLIST_KEY, before);
        return false;
      }
    },
    [client],
  );

  return { ready: query.isSuccess, isSaved, toggle };
}
