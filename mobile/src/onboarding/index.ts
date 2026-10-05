import type { StyleProfileView } from '@/api/types';
import { api } from '@/auth/session';
import { deviceStore } from '@/auth/tokenStore';

import { createOnboarding } from './store';

export const useOnboarding = createOnboarding({
  store: deviceStore,
  fetchProfile: () => api.get<StyleProfileView>('/v1/me/style-profile'),
});
