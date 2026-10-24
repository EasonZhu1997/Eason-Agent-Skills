export declare const EVEROS_SDK_VERSION: '0.1.0';

/** Identifiers are captured at construction; create a new client for a new owner. */
export interface EverosScope {
  appId: string;
  projectId: string;
  userId: string;
  assistantId: string;
}

export interface EverosMessage {
  role: 'user' | 'assistant';
  /** Unix milliseconds, not Unix seconds. */
  timestamp: number;
  content: string;
}

export type EverosSearchMethod = 'keyword' | 'vector' | 'hybrid' | 'agentic';

export interface EverosResult {
  httpStatus: 200 | 202;
  requestId: string;
  /** Provider payload; narrow fields using the current EverOS API contract. */
  data: Record<string, unknown>;
}

/** Errors have a stable message, with this optional delay for HTTP 429 / 503. */
export interface EverosError extends Error {
  retryAfterMs?: number;
}

export interface AIUIRequestResponse {
  statusCode: number;
  data: unknown;
  header?: Record<string, unknown>;
}

export interface AIUIRequestOptions {
  url: string;
  method: 'POST';
  header: Record<string, string>;
  dataType: 'json';
  responseType: 'text';
  timeout: number;
  data: Record<string, unknown>;
  success(response: AIUIRequestResponse): void;
  fail(error?: unknown): void;
}

export interface AIUIRequestTask {
  abort?(): unknown;
}

/** Callback API, matching the portion of AIUI wx.request used by this SDK. */
export type AIUIRequest = (options: AIUIRequestOptions) => AIUIRequestTask | void;

export interface EverosClientOptions {
  /** HTTPS origin only, for example https://api.evermind.ai. No path or query. */
  baseUrl: string;
  scope: EverosScope;
  /** Synchronous runtime supplier; return the complete Bearer header value. */
  getAuthorization(): string;
  /** True only while the captured account / owner epoch remains active. */
  isCurrent(): boolean;
  /** 1..120000 milliseconds; default 10000. */
  timeoutMs?: number;
}

export interface EverosClient {
  /** Synchronous input validation may throw; transport errors reject. */
  add(options: { sessionId: string; messages: EverosMessage[] }): Promise<EverosResult>;
  flush(options: { sessionId: string }): Promise<EverosResult>;
  search(options: {
    query: string;
    method?: EverosSearchMethod;
    topK?: number;
  }): Promise<EverosResult>;
  /** Idempotent. Aborts best-effort; an already sent write may still be applied. */
  dispose(): void;
}

export declare function createEverosClient(
  options: EverosClientOptions & { request: AIUIRequest },
): EverosClient;

export declare function createAIUIEverosClient(
  options: EverosClientOptions & { wx: { request: AIUIRequest } },
): EverosClient;
