# AIUI EverOS SDK · 0.1.0

A dependency-free ES module maintained by Eason for the shared EverOS v2 `add`, `search` and `flush` API subset. It can target Cloud or an authenticated gateway in front of a compatible OSS deployment; verify that deployment's authentication, capabilities and queue behavior first. This is a community AIUI adapter, not an official EverMind or Rokid SDK. The `@eason/aiui-everos` package name identifies this local package; it has not been published to npm.

## Use in AIUI

Copy this **entire `sdk/` directory** into your AIUI project as `lib/everos-sdk/`. Keep the directory together so every agent, Page and Agent Worker imports the same implementation.

```js
import wx from 'wx';
import { createAIUIEverosClient } from './lib/everos-sdk/index.js';

// Supply these values from your authenticated owner session at runtime.
export function createMemoryForOwner({ scope, getAuthorization, isCurrent }) {
  return createAIUIEverosClient({
    wx,
    baseUrl: 'https://api.evermind.ai',
    scope,
    getAuthorization,
    isCurrent,
    timeoutMs: 10000,
  });
}
```

Adjust the relative import to your entry file. Create one client for an authenticated owner epoch, reuse it for that owner's operations, and call `client.dispose()` on logout, owner replacement or the owning component's teardown. Create a new client for the next owner. `getAuthorization()` returns a complete `Bearer …` header synchronously; keep keys and credentials out of source code, logs and shared storage. A shipped client bundle cannot protect a privileged service secret.

```js
const result = await memory.search({ query: 'preferred coaching style', topK: 5 });

// Only after the user's consent and business-side scope checks:
const write = await memory.add({
  sessionId: 'session-001',
  messages: [{ role: 'user', timestamp: Date.now(), content: 'I prefer short prompts.' }],
});
if (write.httpStatus === 200
    && (write.data.status === 'accumulated' || write.data.status === 'extracted')) {
  const flush = await memory.flush({ sessionId: 'session-001' });
  // Inspect flush.httpStatus and flush.data.status before claiming an outcome.
} else {
  // Keep the write receipt for the application's verified task-handling flow.
  // Do not immediately flush or replay a queued / unknown write.
}
```

`memory` above is the client returned by `createMemoryForOwner`. For HTTP `202`, retain `requestId` and confirm processing through the application's bounded task-handling flow using the target deployment's actual task contract before flushing. This SDK does not implement task polling. These calls use the same `appId`, `projectId`, `userId` and `assistantId` captured in `scope` at construction. Sessions must be scoped by the application to that owner. The SDK supplies transport and lifecycle guards; the application supplies consent, authentication and ownership decisions.

## API and outcomes

- `createAIUIEverosClient({ wx, baseUrl, scope, getAuthorization, isCurrent, timeoutMs? })` binds `wx.request` once, preserving its receiver. It needs no `fetch`, Node.js, bundler or external dependencies.
- `createEverosClient({ request, ...options })` keeps the original adapter API for tests or an existing `wx.request` wrapper.
- `add({ sessionId, messages })`, `search({ query, method?, topK? })` and `flush({ sessionId })` return `{ httpStatus, requestId, data }`. See `index.d.ts` for types. There is no automatic retry or persistent queue.
- `dispose()` rejects pending operations with `client_disposed_outcome_unknown`, attempts to abort each request once and discards late callbacks. It is idempotent. Later calls reject with `client_disposed` before sending a request.

Both HTTP `200` and `202` are retained as returned. Inspect the provider's `data.status`; queued, accumulated or `no_extraction` outcomes do not prove that a fact is retrievable. `async_mode: false` is explicit for `add`, but the service can still return `202`. A timeout, network error or disposal after dispatch leaves a write's outcome unknown: aborting cannot roll back a request already accepted by the server. Do not automatically replay it or report it saved. On `http_429` / `http_503`, an optional `error.retryAfterMs` exposes a valid `Retry-After` value without scheduling another call.

Input validation rejects invalid identifiers, non-millisecond timestamps, unsupported roles and oversized messages. Response parsing supports AIUI's parsed JSON, text and legacy `ArrayBuffer` responses with bounded size and structure; legacy binary decoding requires `TextDecoder`. A changed owner discards that owner's late response. These guards do not authorize an owner or make remembered text trusted instructions.

## Local package

For a local package artifact, run from this directory:

```sh
npm pack --dry-run
npm pack --pack-destination /absolute/path/to/artifacts
```

The package includes only the SDK source, type declarations, README, license and package metadata. For AIUI runtime imports, the copied project-local `index.js` is the supported path; do not assume AIUI resolves npm package names. The adjacent `../assets/everos-client.mjs` is only a compatibility re-export and requires this SDK directory.

## Verification and boundaries

Run the repository's synthetic callback tests from the skill root:

```sh
node --test scripts/everos-client.test.mjs scripts/everos-sdk.test.mjs
```

Tests cover the adapter contract, scope guards, validation, HTTP outcomes, timeout, cancellation and concurrent owners. They do not prove network allowlisting, real EverOS credentials or execution on physical glasses. Cloud and current OSS share the v2 subset used here, but deployments can differ in authentication, task support, queue outcomes and additional endpoints. Use a protected HTTPS entry point and verify the deployed contract; an unprotected OSS server is unsuitable as a shared public service. EverMe OAuth MCP is covered by the separate APK skill.

Sources: [EverOS](https://github.com/EverMind-AI/EverOS), [EverOS Cloud documentation](https://docs.evermind.ai/), [AIUI framework and API documentation](https://github.com/yodaos-project/AIUI/tree/main/skills/aiui-dev). MIT license applies to this implementation, not third-party trademarks.
