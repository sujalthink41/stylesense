import { api } from '@/auth/session';

import { createStylistStore } from './store';

/** The app's single stylist session store. */
export const useStylist = createStylistStore(api);
