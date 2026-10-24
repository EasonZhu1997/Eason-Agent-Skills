// AIUI-native EverOS adapter maintained by Eason. No credentials or storage here.
export const EVEROS_SDK_VERSION = '0.1.0';
const ID = /^[A-Za-z0-9_.-]{1,128}$/;
const METHODS = new Set(['keyword', 'vector', 'hybrid', 'agentic']);

function requireId(value) {
  if (typeof value !== 'string' || !ID.test(value) || value === '.' || value === '..') {
    throw new Error('invalid_id');
  }
  return value;
}

function requireText(value) {
  if (typeof value !== 'string' || !value.trim() || value.length > 8000) {
    throw new Error('invalid_text');
  }
  return value;
}

function boundParsedJson(root) {
  const pending = [{ value: root, depth: 0 }];
  const seen = new Set();
  let nodes = 0;
  let textUnits = 0;
  while (pending.length) {
    const { value, depth } = pending.pop();
    if (++nodes > 4096 || depth > 32) throw new Error('response_too_complex');
    if (typeof value === 'string') textUnits += value.length;
    else if (value && typeof value === 'object') {
      if (seen.has(value)) throw new Error('invalid_json_graph');
      seen.add(value);
      const keys = Object.keys(value);
      if (keys.length > 4096 || pending.length + keys.length > 4096) {
        throw new Error('response_too_complex');
      }
      for (const key of keys) {
        textUnits += key.length;
        pending.push({ value: value[key], depth: depth + 1 });
      }
    }
    if (textUnits > 262144) throw new Error('response_too_large');
  }
}

function retryAfterMs(headers) {
  if (!headers || typeof headers !== 'object') return null;
  const key = Object.keys(headers).find(name => name.toLowerCase() === 'retry-after');
  const value = key === undefined ? '' : String(headers[key]).trim();
  if (!value || value.length > 128) return null;
  if (/^\d+$/.test(value)) {
    const delay = Number(value) * 1000;
    return Number.isSafeInteger(delay) ? delay : null;
  }
  // Date.parse accepts non-HTTP strings such as "-1"; accept canonical IMF-fixdate only.
  if (!/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(value)) {
    return null;
  }
  const date = Date.parse(value);
  return Number.isFinite(date) && new Date(date).toUTCString() === value
    ? Math.max(0, date - Date.now()) : null;
}

function parseBody(body) {
  if (body instanceof ArrayBuffer) {
    if (body.byteLength > 262144) throw new Error('response_too_large');
    if (typeof TextDecoder !== 'function') throw new Error('decoder_unavailable');
    body = new TextDecoder('utf-8').decode(body);
  }
  if (typeof body === 'string') {
    if (body.length > 262144) throw new Error('response_too_large');
    body = JSON.parse(body);
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)
      || !body.data || typeof body.data !== 'object' || Array.isArray(body.data)) {
    throw new Error('invalid_envelope');
  }
  boundParsedJson(body);
  return body;
}

export function createEverosClient({
  request, baseUrl, scope, getAuthorization, isCurrent, timeoutMs = 10000,
}) {
  // HTTPS origin only. Never derive it from remembered text or remote model output.
  if (typeof baseUrl !== 'string'
      || !/^https:\/\/[A-Za-z0-9.-]+(?::[0-9]{1,5})?$/.test(baseUrl)) {
    throw new Error('invalid_https_origin');
  }
  if (typeof request !== 'function' || typeof getAuthorization !== 'function'
      || typeof isCurrent !== 'function') throw new Error('missing_adapter');
  if (!Number.isFinite(timeoutMs) || timeoutMs < 1 || timeoutMs > 120000) {
    throw new Error('invalid_timeout');
  }
  const appId = requireId(scope?.appId);
  const projectId = requireId(scope?.projectId);
  const userId = requireId(scope?.userId);
  const assistantId = requireId(scope?.assistantId);
  const inFlight = new Set();
  let disposed = false;
  const current = () => {
    if (disposed) return false;
    try {
      const ownerCurrent = isCurrent() === true;
      return !disposed && ownerCurrent;
    } catch (_) { return false; }
  };
  const inactiveError = () => new Error(disposed ? 'client_disposed' : 'stale_owner');

  function post(operation, payload) {
    return new Promise((resolve, reject) => {
      if (!current()) { reject(inactiveError()); return; }
      let authorization;
      try { authorization = getAuthorization(); }
      catch (_) { reject(new Error('authorization_unavailable')); return; }
      if (typeof authorization !== 'string' || !/^Bearer \S+$/.test(authorization)
          || authorization.length > 8192) {
        reject(new Error('invalid_authorization')); return;
      }
      if (!current()) { reject(inactiveError()); return; }
      let task;
      let settled = false;
      let abortRequested = false;
      let aborted = false;
      let timer;
      const deadline = Date.now() + timeoutMs;
      const pending = { cancel: null };
      const finish = (error, result) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        inFlight.delete(pending);
        if (error) reject(error); else resolve(result);
      };
      const abort = () => {
        abortRequested = true;
        try {
          if (!aborted && task && typeof task.abort === 'function') {
            aborted = true;
            Promise.resolve(task.abort()).catch(() => {});
          }
        } catch (_) {}
      };
      const timedOut = () => {
        finish(new Error('timeout_outcome_unknown'));
        abort();
      };
      pending.cancel = () => {
        finish(new Error('client_disposed_outcome_unknown'));
        abort();
      };
      inFlight.add(pending);
      timer = setTimeout(timedOut, timeoutMs);
      try {
        task = request({
          url: baseUrl + '/api/v2/memory/' + operation,
          method: 'POST',
          header: { 'Content-Type': 'application/json', Authorization: authorization },
          dataType: 'json', responseType: 'text', timeout: timeoutMs,
          data: { ...payload, app_id: appId, project_id: projectId },
          success(response) {
            if (settled) return;
            if (!current()) { finish(inactiveError()); return; }
            if (Date.now() >= deadline) { timedOut(); return; }
            if (response?.statusCode !== 200 && response?.statusCode !== 202) {
              const error = new Error('http_' + (Number(response?.statusCode) || 0));
              if (response?.statusCode === 429 || response?.statusCode === 503) {
                const delay = retryAfterMs(response.header);
                if (delay !== null) error.retryAfterMs = delay;
              }
              finish(error); return;
            }
            try {
              const body = parseBody(response.data);
              finish(null, {
                httpStatus: response.statusCode,
                requestId: typeof body.request_id === 'string' ? body.request_id : '',
                data: body.data,
              });
            } catch (_) { finish(new Error('invalid_json_response')); }
          },
          fail() { finish(new Error('network_outcome_unknown')); },
        });
        // A reentrant dispose() may run inside a custom request adapter, before
        // it has returned its RequestTask. Abort that task as soon as available.
        if (abortRequested) abort();
      } catch (_) { finish(new Error('request_failed')); }
    });
  }

  return {
    add({ sessionId, messages }) {
      requireId(sessionId);
      if (!Array.isArray(messages) || !messages.length || messages.length > 500) {
        throw new Error('invalid_messages');
      }
      const normalized = Array.from(messages, message => {
        if (!message || typeof message !== 'object' || Array.isArray(message)) {
          throw new Error('invalid_messages');
        }
        const { role, timestamp, content } = message;
        if (role !== 'user' && role !== 'assistant') throw new Error('invalid_role');
        if (!Number.isSafeInteger(timestamp) || timestamp < 1000000000000) {
          throw new Error('invalid_millisecond_timestamp');
        }
        return { sender_id: role === 'user' ? userId : assistantId,
          role, timestamp, content: requireText(content) };
      });
      return post('add', { session_id: sessionId, messages: normalized, async_mode: false });
    },
    flush({ sessionId }) {
      return post('flush', { session_id: requireId(sessionId) });
    },
    search({ query, method = 'keyword', topK = 5 }) {
      if (!METHODS.has(method) || !Number.isInteger(topK) || topK < 1 || topK > 100) {
        throw new Error('invalid_search_options');
      }
      return post('search', { user_id: userId, query: requireText(query),
        method, top_k: topK, include_profile: true });
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      for (const pending of [...inFlight]) pending.cancel();
    },
  };
}

export function createAIUIEverosClient({ wx, ...options }) {
  if (!wx || typeof wx.request !== 'function') throw new Error('missing_wx_request');
  return createEverosClient({ ...options, request: wx.request.bind(wx) });
}
