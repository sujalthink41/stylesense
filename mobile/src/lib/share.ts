import { Share } from 'react-native';

import { api } from '@/auth/session';

export interface ShareView {
  slug: string;
  kind: 'look' | 'product' | 'board';
  url: string;
  title: string | null;
  views: number;
}

export type ShareTarget =
  | { kind: 'product'; productId: string; title?: string }
  | { kind: 'look'; productIds: string[]; title?: string }
  | { kind: 'board'; boardId: string; title?: string };

/** Get the link (same thing → same link, server-side) and open the system share sheet. */
export async function shareLink(target: ShareTarget, message: string): Promise<ShareView> {
  const body =
    target.kind === 'board'
      ? { kind: 'board', board_id: target.boardId, title: target.title }
      : { kind: target.kind, product_ids: target.kind === 'product' ? [target.productId] : target.productIds, title: target.title };
  const share = await api.post<ShareView>('/v1/shares', body);
  await Share.share({ message: `${message}\n${share.url}`, url: share.url });
  return share;
}
