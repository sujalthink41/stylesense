import { ApiError, networkError, problemFrom } from './errors';
import { SSEParser, type SSEEvent } from './sse';

export interface TokenSource {
  /** Current access token, if signed in. */
  accessToken(): string | null;
  /** Gets fresh tokens with the refresh token; resolves false when the session is over. */
  refresh(): Promise<boolean>;
}

export interface RequestOptions {
  body?: unknown;
  /** Defaults to true: attach the access token and refresh once on 401. */
  auth?: boolean;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface ApiClientConfig {
  baseUrl: string;
  tokens: TokenSource;
  /** Sent on every request; the server negotiates GenUI components against it. */
  genuiVersion: number;
  appVersion: string;
  fetchImpl?: typeof fetch;
  defaultTimeoutMs?: number;
}

/**
 * One HTTP client for the whole app: timeouts, problem+json errors, and a single-flight token
 * refresh so ten parallel requests that hit 401 trigger one refresh, not ten.
 */
export class ApiClient {
  private refreshing: Promise<boolean> | null = null;
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly config: ApiClientConfig) {
    this.fetchImpl = config.fetchImpl ?? ((input, init) => fetch(input, init));
  }

  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>('GET', path, options);
  }

  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>('POST', path, { ...options, body });
  }

  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>('PUT', path, { ...options, body });
  }

  delete<T = void>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>('DELETE', path, options);
  }

  async request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    return this.parse<T>(await this.respond(method, path, options));
  }

  /**
   * POST that asks for Server-Sent Events and hands each one to `onEvent` as it arrives.
   * A proxy may buffer and answer plain JSON instead; that body is returned as is.
   * Once the server has accepted the request, a dropped or silent stream throws `stream_lost`:
   * the work carries on server-side, so the caller should resume, not resend.
   */
  async events<T>(
    path: string,
    body: unknown,
    onEvent: (event: SSEEvent) => void,
    { idleTimeoutMs = 45_000, ...options }: RequestOptions & { idleTimeoutMs?: number } = {},
  ): Promise<{ streamed: true } | { streamed: false; body: T }> {
    const response = await this.respond('POST', path, {
      ...options,
      body,
      headers: { ...options.headers, Accept: 'text/event-stream' },
    });
    if (!response.ok || !(response.headers.get('Content-Type') ?? '').includes('text/event-stream')) {
      return { streamed: false, body: await this.parse<T>(response) };
    }
    const parser = new SSEParser();
    const reader = response.body?.getReader();
    try {
      if (!reader) {
        // No incremental body here: everything arrives at the end, still in order.
        [...parser.feed(await response.text()), ...parser.flush()].forEach(onEvent);
        return { streamed: true };
      }
      const decoder = new TextDecoder();
      for (;;) {
        const { done, value } = await withIdleLimit(reader.read(), idleTimeoutMs, () => void reader.cancel());
        if (done) break;
        parser.feed(decoder.decode(value, { stream: true })).forEach(onEvent);
      }
      parser.flush().forEach(onEvent);
      return { streamed: true };
    } catch (error) {
      if (error instanceof ApiError && error.code !== 'stream_lost') throw error;
      throw new ApiError({ status: 0, code: 'stream_lost', title: 'Connection lost' });
    }
  }

  private async respond(method: string, path: string, options: RequestOptions): Promise<Response> {
    const auth = options.auth ?? true;
    const first = await this.send(method, path, options, auth);
    if (first.status === 401 && auth && this.config.tokens.accessToken() && (await this.refreshOnce())) {
      return this.send(method, path, options, auth);
    }
    return first;
  }

  private refreshOnce(): Promise<boolean> {
    if (!this.refreshing) {
      this.refreshing = this.config.tokens.refresh().finally(() => {
        this.refreshing = null;
      });
    }
    return this.refreshing;
  }

  private async send(method: string, path: string, options: RequestOptions, auth: boolean): Promise<Response> {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      'X-GenUI-Version': String(this.config.genuiVersion),
      'X-App-Version': this.config.appVersion,
      ...options.headers,
    };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    const token = auth ? this.config.tokens.accessToken() : null;
    if (token) headers.Authorization = `Bearer ${token}`;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? this.config.defaultTimeoutMs ?? 20_000);
    const onAbort = () => controller.abort();
    options.signal?.addEventListener('abort', onAbort);
    try {
      return await this.fetchImpl(`${this.config.baseUrl}${path}`, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
    } catch {
      if (options.signal?.aborted) throw new ApiError({ status: 0, code: 'cancelled', title: 'Cancelled' });
      throw networkError(controller.signal.aborted ? 'timeout' : 'offline');
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener('abort', onAbort);
    }
  }

  private async parse<T>(response: Response): Promise<T> {
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    let body: unknown = undefined;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = undefined;
      }
    }
    if (!response.ok) throw problemFrom(response.status, body, response.headers.get('Retry-After'));
    return body as T;
  }
}

/** Rejects with `stream_lost` when `read` takes longer than `ms` (keep-alives arrive every 15 s). */
function withIdleLimit<T>(read: Promise<T>, ms: number, onTimeout: () => void): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const idle = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      onTimeout();
      reject(new ApiError({ status: 0, code: 'stream_lost', title: 'Connection lost' }));
    }, ms);
  });
  return Promise.race([read, idle]).finally(() => clearTimeout(timer));
}
