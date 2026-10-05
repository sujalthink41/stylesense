import { ApiError, networkError, problemFrom } from './errors';

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
    const auth = options.auth ?? true;
    const first = await this.send(method, path, options, auth);
    if (first.status === 401 && auth && this.config.tokens.accessToken()) {
      if (await this.refreshOnce()) {
        return this.parse<T>(await this.send(method, path, options, auth));
      }
    }
    return this.parse<T>(first);
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
