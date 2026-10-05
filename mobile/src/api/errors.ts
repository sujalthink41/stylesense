/** Every failure the app can meet, as one type: RFC 9457 problems from the API, plus our own. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string | undefined;
  readonly extra: Record<string, unknown>;
  readonly retryAfterS: number | undefined;

  constructor(init: {
    status: number;
    code: string;
    title: string;
    detail?: string;
    extra?: Record<string, unknown>;
    retryAfterS?: number;
  }) {
    super(init.detail ?? init.title);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.title = init.title;
    this.detail = init.detail;
    this.extra = init.extra ?? {};
    this.retryAfterS = init.retryAfterS;
  }

  /** No response at all: offline, DNS, timeout. Worth retrying. */
  get isNetwork(): boolean {
    return this.status === 0;
  }
}

const RESERVED = new Set(['type', 'title', 'status', 'detail', 'instance', 'code', 'request_id']);

/** Parses a problem+json body (or anything else) into an ApiError. */
export function problemFrom(status: number, body: unknown, retryAfter: string | null): ApiError {
  const obj = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
  const extra: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) if (!RESERVED.has(k)) extra[k] = v;
  const retry = retryAfter != null && /^\d+$/.test(retryAfter) ? Number(retryAfter) : undefined;
  return new ApiError({
    status,
    code: typeof obj.code === 'string' ? obj.code : `http_${status}`,
    title: typeof obj.title === 'string' ? obj.title : 'Something went wrong',
    detail: typeof obj.detail === 'string' ? obj.detail : undefined,
    extra,
    retryAfterS: retry,
  });
}

export function networkError(reason: 'offline' | 'timeout'): ApiError {
  return new ApiError({
    status: 0,
    code: reason,
    title: reason === 'timeout' ? 'That took too long' : "You're offline",
    detail:
      reason === 'timeout'
        ? 'The connection is slow right now. Try again.'
        : 'Check your connection and try again.',
  });
}

/** A short, human message for UI. Codes the user can act on get their own words. */
export function friendlyMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Something went wrong. Try again.';
  switch (error.code) {
    case 'offline':
    case 'timeout':
      return error.detail ?? error.title;
    case 'rate_limited':
      return 'Too many tries at once. Wait a moment and try again.';
    case 'daily_limit':
      return "You've reached today's limit. Try again tomorrow.";
    case 'app_update_required':
      return 'Please update StyleSense to keep going.';
    default:
      return error.detail ?? error.title;
  }
}
