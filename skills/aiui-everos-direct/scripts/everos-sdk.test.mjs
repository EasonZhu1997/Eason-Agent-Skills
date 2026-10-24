import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createAIUIEverosClient, createEverosClient, EVEROS_SDK_VERSION,
} from '../sdk/index.js';
import * as legacy from '../assets/everos-client.mjs';

const scope = { appId: 'demo', projectId: 'test', userId: 'owner-one', assistantId: 'assistant' };
const turn = { role: 'user', timestamp: 1792800000000, content: 'synthetic preference' };
const options = overrides => ({
  baseUrl: 'https://memory.example.com', scope,
  getAuthorization: () => 'Bearer synthetic-only', isCurrent: () => true,
  timeoutMs: 1000, ...overrides,
});
function answer(request, data = { episodes: [] }) {
  request.success({ statusCode: 200, data: { data } });
}

test('compatibility entry re-exports the canonical versioned SDK', () => {
  assert.equal(legacy.createEverosClient, createEverosClient);
  assert.equal(legacy.createAIUIEverosClient, createAIUIEverosClient);
  assert.equal(legacy.EVEROS_SDK_VERSION, EVEROS_SDK_VERSION);
  assert.equal(EVEROS_SDK_VERSION, '0.1.0');
});

test('AIUI factory binds wx.request once and preserves its receiver', async () => {
  let calls = 0;
  const wx = { request(request) {
    assert.equal(this, wx);
    calls++;
    answer(request);
  } };
  const client = createAIUIEverosClient({ ...options(), wx });
  wx.request = () => { throw new Error('replaced request should not run'); };
  await client.search({ query: 'preference' });
  await client.search({ query: 'coaching' });
  assert.equal(calls, 2);
  assert.throws(() => createAIUIEverosClient({ ...options(), wx: {} }), /missing_wx_request/);
});

test('dispose before use is idempotent and prevents credential lookup and dispatch', async () => {
  let dispatched = 0;
  let credentialReads = 0;
  const client = createEverosClient({ ...options({ getAuthorization() {
    credentialReads++;
    return 'Bearer synthetic-only';
  } }), request() { dispatched++; } });
  client.dispose();
  client.dispose();
  await assert.rejects(client.search({ query: 'preference' }), /^Error: client_disposed$/);
  await assert.rejects(client.add({ sessionId: 'session', messages: [turn] }), /^Error: client_disposed$/);
  assert.equal(dispatched, 0);
  assert.equal(credentialReads, 0);
});

test('dispose rejects every pending operation and aborts once before ignoring late callbacks', async () => {
  const pending = [];
  let aborts = 0;
  const client = createEverosClient({ ...options(), request(request) {
    pending.push(request);
    return { abort() {
      aborts++;
      answer(request, { status: 'extracted' });
      request.fail();
      return Promise.reject(new Error('synthetic abort failure'));
    } };
  } });
  const operations = [
    client.search({ query: 'preference' }),
    client.add({ sessionId: 'session', messages: [turn] }),
    client.flush({ sessionId: 'session' }),
  ];
  const outcomes = operations.map(operation => assert.rejects(operation,
    /^Error: client_disposed_outcome_unknown$/));
  client.dispose();
  client.dispose();
  await Promise.all(outcomes);
  for (const request of pending) answer(request, { status: 'saved' });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(aborts, 3);
  assert.equal(pending.length, 3);
});

test('reentrant disposal aborts the RequestTask returned after cancellation', async () => {
  let client;
  let aborts = 0;
  client = createEverosClient({ ...options(), request() {
    client.dispose();
    return { abort() { aborts++; } };
  } });
  await assert.rejects(client.search({ query: 'preference' }), /client_disposed_outcome_unknown/);
  assert.equal(aborts, 1);
});

test('dispose does not abort an already completed request', async () => {
  let aborts = 0;
  const client = createEverosClient({ ...options(), request(request) {
    answer(request);
    return { abort() { aborts++; } };
  } });
  await client.search({ query: 'preference' });
  client.dispose();
  assert.equal(aborts, 0);
});

test('concurrent owners keep captured scope, callbacks and disposal isolated', async () => {
  const calls = [];
  const aborts = [];
  const request = call => {
    calls.push(call);
    return { abort() { aborts.push(call.data.user_id); } };
  };
  const mutableScope = { ...scope };
  const first = createEverosClient({ ...options({ scope: mutableScope }), request });
  const second = createEverosClient({ ...options({ scope: { ...scope, userId: 'owner-two' },
    getAuthorization: () => 'Bearer synthetic-two' }), request });
  mutableScope.userId = 'mutated-owner';
  const firstResult = first.search({ query: 'first' });
  const firstRejection = assert.rejects(firstResult, /client_disposed_outcome_unknown/);
  const secondResult = second.search({ query: 'second' });
  first.dispose();
  answer(calls[0], { episodes: [{ summary: 'late first-owner data' }] });
  answer(calls[1], { episodes: [{ summary: 'second-owner data' }] });
  await firstRejection;
  assert.equal((await secondResult).data.episodes[0].summary, 'second-owner data');
  assert.equal(calls[0].data.user_id, 'owner-one');
  assert.equal(calls[1].data.user_id, 'owner-two');
  assert.equal(calls[1].header.Authorization, 'Bearer synthetic-two');
  assert.deepEqual(aborts, ['owner-one']);
  second.dispose();
});

test('out-of-order concurrent operations retain their own session and result', async () => {
  const calls = [];
  const client = createEverosClient({ ...options(), request(request) { calls.push(request); } });
  const first = client.flush({ sessionId: 'session-one' });
  const second = client.flush({ sessionId: 'session-two' });
  answer(calls[1], { status: 'queued', marker: 'two' });
  answer(calls[0], { status: 'no_extraction', marker: 'one' });
  assert.equal((await first).data.marker, 'one');
  assert.equal((await second).data.marker, 'two');
  assert.deepEqual(calls.map(call => call.data.session_id), ['session-one', 'session-two']);
  client.dispose();
});

test('each operation reads current runtime credentials without storing a token', async () => {
  let authorization = 'Bearer synthetic-first';
  const headers = [];
  const client = createEverosClient({ ...options({ getAuthorization: () => authorization }),
    request(request) { headers.push(request.header.Authorization); answer(request); } });
  await client.search({ query: 'first' });
  authorization = 'Bearer synthetic-next';
  await client.search({ query: 'second' });
  assert.deepEqual(headers, ['Bearer synthetic-first', 'Bearer synthetic-next']);
  client.dispose();
});

test('disposed owner guard cannot reentrantly authorize a new request', async () => {
  let client;
  let dispatched = 0;
  client = createEverosClient({ ...options({ isCurrent() { client.dispose(); return true; } }),
    request() { dispatched++; } });
  await assert.rejects(client.search({ query: 'preference' }), /^Error: client_disposed$/);
  assert.equal(dispatched, 0);
});

test('network failure of a write remains unknown and is never automatically replayed', async () => {
  let calls = 0;
  const client = createEverosClient({ ...options(), request(request) {
    calls++;
    request.fail({ errMsg: 'synthetic private transport detail' });
  } });
  await assert.rejects(client.add({ sessionId: 'session', messages: [turn] }),
    /^Error: network_outcome_unknown$/);
  assert.equal(calls, 1);
  client.dispose();
});

test('dispose tolerates absent and throwing abort methods while settling the promise', async () => {
  for (const task of [undefined, {}, { abort() { throw new Error('synthetic abort throw'); } }]) {
    const client = createEverosClient({ ...options(), request() { return task; } });
    const result = client.flush({ sessionId: 'session' });
    const rejection = assert.rejects(result, /^Error: client_disposed_outcome_unknown$/);
    assert.doesNotThrow(() => client.dispose());
    await rejection;
  }
});
