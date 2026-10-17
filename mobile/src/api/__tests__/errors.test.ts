import { ApiError, friendlyMessage, networkError, problemFrom } from '@/api/errors';

const problem = (code: string, detail?: string) => new ApiError({ status: 400, code, title: 'Title', detail });

describe('friendlyMessage', () => {
  it.each([
    ['rate_limited', 'Too many tries'],
    ['daily_limit', "today's limit"],
    ['permission_denied', 'camera or photos'],
    ['upload_failed', "didn't upload"],
    ['photo_rejected', 'well-lit photo'],
    ['tryon_unavailable', 'studio is busy'],
    ['app_update_required', 'update StyleSense'],
  ])('%s gets words a shopper can act on', (code, words) => {
    expect(friendlyMessage(problem(code))).toContain(words);
  });

  it('shows the server’s own try-on limit message, with a fallback', () => {
    expect(friendlyMessage(problem('tryon_daily_limit', 'More from 7:30 pm.'))).toBe('More from 7:30 pm.');
    expect(friendlyMessage(problem('tryon_daily_limit'))).toContain('Come back tomorrow');
  });

  it('explains network failures and falls back to the problem text', () => {
    expect(friendlyMessage(networkError('timeout'))).toContain('slow');
    expect(friendlyMessage(networkError('offline'))).toContain('connection');
    expect(friendlyMessage(problem('something_new', 'Exact detail'))).toBe('Exact detail');
    expect(friendlyMessage(problem('something_new'))).toBe('Title');
    expect(friendlyMessage(new Error('boom'))).toBe('Something went wrong. Try again.');
  });
});

describe('problemFrom', () => {
  it('keeps extra fields and a numeric Retry-After', () => {
    const e = problemFrom(429, { code: 'tryon_daily_limit', title: 'Limit', limit: 3, request_id: 'r' }, '60');
    expect([e.code, e.retryAfterS, e.extra]).toEqual(['tryon_daily_limit', 60, { limit: 3 }]);
    expect(e.isNetwork).toBe(false);
  });

  it('copes with a body that is not a problem', () => {
    const e = problemFrom(502, '<html>', 'soon');
    expect([e.code, e.title, e.retryAfterS]).toEqual(['http_502', 'Something went wrong', undefined]);
  });
});
