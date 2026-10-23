import test from 'node:test';
import assert from 'node:assert/strict';
import { createEverosClient } from '../assets/everos-client.mjs';

const scope = { appId: 'demo', projectId: 'test', userId: 'test-user', assistantId: 'assistant' };
const turn = { role: 'user', timestamp: 1792800000000, content: '合成测试偏好' };
function client(request, overrides = {}) {
  return createEverosClient({ request, baseUrl: 'https://memory.example.com', scope,
    getAuthorization: () => 'Bearer synthetic-test-only', isCurrent: () => true,
    timeoutMs: 100, ...overrides });
}
function answer(options, data, statusCode = 200) {
  options.success({ statusCode, data: { request_id: 'synthetic-request', data } });
}

test('write pins scope and speaker identity; milliseconds and explicit sync mode', async () => {
  let seen;
  const c = client(options => { seen = options; answer(options, { status: 'accumulated' }); });
  const r = await c.add({ sessionId: 'test-session', messages: [turn] });
  assert.equal(seen.url, 'https://memory.example.com/api/v2/memory/add');
  assert.equal(seen.data.messages[0].sender_id, 'test-user');
  assert.equal(seen.data.app_id, 'demo');
  assert.equal(seen.data.project_id, 'test');
  assert.equal(seen.data.async_mode, false);
  assert.equal(seen.responseType, 'text');
  assert.equal(r.data.status, 'accumulated');
});

test('202 remains queued and retains task handle', async () => {
  const r = await client(o => answer(o, { status: 'queued' }, 202))
    .add({ sessionId: 'test-session', messages: [turn] });
  assert.equal(r.httpStatus, 202);
  assert.equal(r.data.status, 'queued');
  assert.equal(r.requestId, 'synthetic-request');
});

test('search uses same user scope and safe explicit method', async () => {
  let seen;
  await client(o => { seen = o; answer(o, { episodes: [], profiles: [] }); }).search({ query: '偏好' });
  assert.equal(seen.data.user_id, 'test-user');
  assert.equal(seen.data.agent_id, undefined);
  assert.equal(seen.data.method, 'keyword');
});

test('flush preserves session scope and no_extraction status', async () => {
  let seen;
  const r = await client(o => { seen = o; answer(o, { status: 'no_extraction' }); })
    .flush({ sessionId: 'test-session' });
  assert.equal(seen.data.session_id, 'test-session');
  assert.equal(seen.data.project_id, 'test');
  assert.equal(r.data.status, 'no_extraction');
});

test('parses text and old-host ArrayBuffer with Chinese UTF-8 content', async () => {
  const episodes = [{ summary: '偏好简短中文提醒' }];
  for (const data of [JSON.stringify({ data: { episodes } }),
    new TextEncoder().encode(JSON.stringify({ data: { episodes } })).buffer]) {
    const r = await client(o => o.success({ statusCode: 200, data })).search({ query: '偏好' });
    assert.deepEqual(r.data.episodes, episodes);
  }
});

test('HTTP authorization failure is not treated as success', async () => {
  await assert.rejects(client(o => answer(o, {}, 401)).search({ query: '偏好' }), /http_401/);
});

test('malformed JSON and wrong envelope reject without echoing private body', async () => {
  for (const data of ['not-json', {}, { data: [] }]) {
    await assert.rejects(client(o => o.success({ statusCode: 200, data })).search({ query: '偏好' }),
      /invalid_json_response/);
  }
});

test('identity change during request discards old response', async () => {
  let active = true;
  let callback;
  const promise = client(o => { callback = o; }, { isCurrent: () => active }).search({ query: '偏好' });
  active = false;
  answer(callback, { episodes: [{ summary: 'old owner data' }] });
  await assert.rejects(promise, /stale_owner/);
});

test('identity guard failure prevents dispatch', async () => {
  let calls = 0;
  await assert.rejects(client(() => { calls++; }, { isCurrent: () => false }).search({ query: '偏好' }), /stale_owner/);
  assert.equal(calls, 0);
});

test('deadline aborts and late callback cannot resurrect result', async () => {
  let callback;
  let aborts = 0;
  const c = client(o => { callback = o; return { abort() { aborts++; } }; }, { timeoutMs: 5 });
  await assert.rejects(c.search({ query: '偏好' }), /timeout_outcome_unknown/);
  answer(callback, { episodes: [] });
  assert.equal(aborts, 1);
});

test('abort synchronous callback and rejected abort promise do not settle twice', async () => {
  let callback;
  const c = client(o => { callback = o; return { abort() {
    answer(callback, { episodes: [{ summary: 'late' }] });
    callback.fail();
    return Promise.reject(new Error('synthetic abort rejection'));
  } }; }, { timeoutMs: 5 });
  await assert.rejects(c.search({ query: '偏好' }), /timeout_outcome_unknown/);
  await new Promise(resolve => setTimeout(resolve, 0));
});

test('oversized ArrayBuffer is rejected before decode', async () => {
  await assert.rejects(client(o => o.success({ statusCode: 200, data: new ArrayBuffer(262145) }))
    .search({ query: '偏好' }), /invalid_json_response/);
});

test('rejects secret-bearing URL, HTTP URL and invalid inputs before dispatch', () => {
  assert.throws(() => client(() => {}, { baseUrl: 'https://user:password@example.com' }), /invalid_https_origin/);
  assert.throws(() => client(() => {}, { baseUrl: 'http://example.com' }), /invalid_https_origin/);
  const c = client(() => {});
  assert.throws(() => c.add({ sessionId: 'test', messages: [{ ...turn, timestamp: 1792800000 }] }), /millisecond/);
  assert.throws(() => c.search({ query: '偏好', topK: 101 }), /invalid_search_options/);
});

test('missing runtime credentials fail before dispatch', async () => {
  let calls = 0;
  await assert.rejects(client(() => { calls++; }, { getAuthorization: () => '' }).search({ query: '偏好' }),
    /invalid_authorization/);
  assert.equal(calls, 0);
});

test('sparse or invalid message entries reject before any request is sent', () => {
  let calls = 0;
  const c = client(() => { calls++; });
  const sparse = [turn];
  sparse.length = 2;
  for (const messages of [new Array(1), sparse, [undefined], [null], [[]], ['text']]) {
    assert.throws(() => c.add({ sessionId: 'test-session', messages }), /invalid_messages/);
  }
  assert.equal(calls, 0);
});

test('already parsed JSON cannot bypass total content, depth or node budgets', async () => {
  const oversized = { episodes: [{ summary: 'x'.repeat(300000) }] };
  let deep = { summary: 'small' };
  for (let i = 0; i < 40; i++) deep = { nested: deep };
  const many = { episodes: Array.from({ length: 5000 }, () => ({ summary: 'x' })) };
  for (const data of [oversized, deep, many]) {
    await assert.rejects(client(o => answer(o, data)).search({ query: '偏好' }),
      /invalid_json_response/);
  }
});

test('rate limit exposes only parsed Retry-After delay, without retrying', async () => {
  let calls = 0;
  await assert.rejects(client(o => {
    calls++;
    o.success({ statusCode: 429, header: { 'rEtRy-AfTeR': '120', private: 'do-not-expose' }, data: {} });
  }).search({ query: '偏好' }), error => {
    assert.equal(error.message, 'http_429');
    assert.equal(error.retryAfterMs, 120000);
    assert.deepEqual(Object.keys(error), ['retryAfterMs']);
    return true;
  });
  assert.equal(calls, 1);
});

test('service Retry-After HTTP date is usable and invalid values are omitted', async () => {
  const date = new Date(Date.now() + 120000).toUTCString();
  for (const value of [date, 'not-a-date', '-1', '1.5']) {
    await assert.rejects(client(o => o.success({ statusCode: 503,
      header: { 'Retry-After': value }, data: {} })).search({ query: '偏好' }), error => {
      if (value === date) assert.ok(error.retryAfterMs > 118000 && error.retryAfterMs <= 120000);
      else assert.equal(error.retryAfterMs, undefined);
      return true;
    });
  }
});
