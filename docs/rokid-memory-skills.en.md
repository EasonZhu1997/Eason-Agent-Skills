# Add long-term memory to Rokid apps

[简体中文](rokid-memory-skills.md) · **English** · [日本語](rokid-memory-skills.ja.md)

<p>
  <img src="assets/brand/rokid-logo-black-on-white.svg" height="64" alt="Rokid standard logo" />
  &nbsp;&nbsp;
  <img src="assets/brand/evermind-logo.png" height="64" alt="EverMind logo" />
</p>

Start with your app's execution path, then build one small **recall → answer → remember** loop. These two development skills help an AI coding assistant implement the integration in your project. They do not install a memory runtime on the glasses.

## 1. Choose a route

```mermaid
%%{init: {"theme":"base","htmlLabels":false,"flowchart":{"wrappingWidth":240},"themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#EEF4FF","primaryTextColor":"#172033","primaryBorderColor":"#2F63E8","lineColor":"#526078","clusterBkg":"#F7F9FD","clusterBorder":"#B9C9E7"}}}%%
flowchart TB
    Q{"Where does your app run?"}
    Q -->|AIUI on glasses| A["aiui-everos-direct"]
    Q -->|Android companion app| B["apk-everme-oauth"]
    A --> C["EverOS HTTP API<br/>Cloud or protected self-hosting"]
    B --> D["EverMe personal account<br/>OAuth and remote MCP"]
    classDef component fill:#EEF4FF,stroke:#2F63E8,color:#172033
    classDef step fill:#FFF1E8,stroke:#E64A19,color:#172033
    class A,B,C,D component
    class Q step
```

| Your starting point | Use this skill | Prepare first |
| --- | --- | --- |
| AIUI app; no phone relay required | [AIUI × EverOS](../skills/aiui-everos-direct/SKILL.md) | AIUI host version, reachable HTTPS service, runtime credentials, stable app user identity |
| Android APK assisting Rokid glasses | [APK × EverMe](../skills/apk-everme-oauth/SKILL.md) | App login, backend, existing glasses connection, EverMe onboarding and user consent |

**EverOS** is the HTTP memory service in the first route. **EverMe** is the personal-account service in the second. Confirm the actual service when a project calls it “Evermate” or “Evermind OS.” An EverOS API key does not replace EverMe user authorization.

Blue boxes represent components. Orange marks a decision or an operation. The diagrams show integration designs, not completed deployments.

## 2. AIUI route: connect without a companion APK

The diagram shows the recommended arrangement for an app distributed to multiple users. The gateway belongs to your application; it authenticates the app user and keeps the upstream master key on the server.

```mermaid
%%{init: {"theme":"base","htmlLabels":false,"flowchart":{"wrappingWidth":240},"themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#EEF4FF","primaryTextColor":"#172033","primaryBorderColor":"#2F63E8","lineColor":"#526078","clusterBkg":"#F7F9FD","clusterBorder":"#B9C9E7"}}}%%
flowchart TB
    subgraph Device["Rokid glasses"]
        A["AIUI Page / Widget / Agent Worker"]
        K["Shared EverOS JavaScript SDK<br/>Version 0.1.0"]
        A -->|add / search / flush| K
    end
    subgraph Backend["Your service boundary"]
        G["Authenticated memory gateway<br/>Bind user and data scope"]
    end
    subgraph Memory["Choose one deployment"]
        C["EverOS Cloud v2"]
        S["Protected self-hosted EverOS v2"]
    end
    K -->|wx.request with app credentials| G
    G -->|Cloud credentials| C
    G -->|Configured service authentication| S
    classDef component fill:#EEF4FF,stroke:#2F63E8,color:#172033
    class A,G,C,S component
```

For personal development, a developer may supply their own Cloud key at runtime. **Do not embed a shared key in a public AIX.** “Direct” means no APK relay; a gateway can still be part of the path. An unprotected self-hosted localhost service is not a suitable public endpoint, and `user_id` alone is not access control.

Build the first loop with `POST /api/v2/memory/search`, generate a reply, then submit permitted conversation events with `POST /api/v2/memory/add`. Use `flush` at a session boundary when extraction is needed. Pin `app_id`, `project_id`, user identity and session identity; raw message timestamps use **Unix milliseconds**. On a self-hosted deployment without embeddings, explicitly choose `keyword` search.

Start here: [versions and deployment](../skills/aiui-everos-direct/references/versions-and-sources.md), [v2 requests and response states](../skills/aiui-everos-direct/references/api-v2.md), [AIUI adapter](../skills/aiui-everos-direct/references/aiui-adapter.md).

### Reuse the JavaScript SDK

The Skill now reuses a versioned [AIUI EverOS SDK](../skills/aiui-everos-direct/sdk/README.md) rather than generating a new HTTP client for each project. The single implementation contains request construction, response parsing, identity checks, timeouts and cleanup. Your app supplies its service address, user identity, runtime credentials and lifecycle wiring.

1. Download the SDK from the [v0.1.0 release](https://github.com/EasonZhu1997/Eason-Agent-Skills/releases/tag/aiui-everos-sdk-v0.1.0), or copy the complete `skills/aiui-everos-direct/sdk/` directory.
2. Put that directory at your AIUI project's `lib/everos-sdk/`, retaining `package.json` and `LICENSE`.
3. Import the `.js` module and configure it. The following wiring fragment assumes the app has supplied `memoryConfig`; credentials come from its runtime callback.

```js
import wx from 'wx';
import { createAIUIEverosClient } from '../../lib/everos-sdk/index.js';

const memory = createAIUIEverosClient({ wx, ...memoryConfig });
const result = await memory.search({ query: 'reminder preferences' });
```

`memoryConfig` contains `baseUrl`, `scope: {appId, projectId, userId, assistantId}`, a synchronous `getAuthorization()` returning the full Bearer value, and `isCurrent()` checking the captured user/authorization generation; `timeoutMs` is optional. Supply these from the app's existing login and service configuration. Keep shared keys out of source code.

| SDK method | Application responsibility |
| --- | --- |
| `search({query, method, topK})` | Use bounded results only for the current user |
| `add({sessionId, messages})` | Submit permitted user/assistant messages with millisecond timestamps |
| `flush({sessionId})` | Request extraction at the appropriate session boundary |
| `dispose()` | Release an instance when its page, user or authorization ends |

Call `dispose()` in Page `onUnload()` or Widget `onDestroy()`; create a new instance when needed again. Cancellation cannot undo a write already sent. The SDK is a community AIUI adapter maintained in this repository; its package name is not a claim of an npm publication. [SDK source](../skills/aiui-everos-direct/sdk/index.js) · [Type declarations](../skills/aiui-everos-direct/sdk/index.d.ts).

## 3. APK route: use the user's EverMe account

```mermaid
%%{init: {"theme":"base","htmlLabels":false,"flowchart":{"wrappingWidth":240},"themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#EEF4FF","primaryTextColor":"#172033","primaryBorderColor":"#2F63E8","lineColor":"#526078","clusterBkg":"#F7F9FD","clusterBorder":"#B9C9E7"}}}%%
flowchart TB
    R["Rokid glasses<br/>Voice and display"]
    A["Android companion APK<br/>Login and connection UI"]
    B["Your backend<br/>Account binding and token storage"]
    E["EverMe OAuth MCP<br/>Authorized personal memory"]
    R <-->|Existing device channel| A
    A <-->|HTTPS with app login| B
    B <-->|User-scoped bearer token and MCP| E
    classDef component fill:#EEF4FF,stroke:#2F63E8,color:#172033
    class R,A,B,E component
```

EverMe does not create your Bluetooth connection, microphone pipeline, TTS or HUD integration. Reuse and verify those parts of your existing Rokid app.

Before dynamic client registration (**DCR**), register the exact callback URLs for your environments with EverMe and agree on a fixed `client_name`. Discover the official OAuth endpoints, persist the client registration and request only the scopes you need. Save the **granted** scopes returned by authorization; a write operation requires `mem:write`.

### The authorization return must reach the initiating app

This is the App Link completion option for the backend proxy design. A trusted browser session bound to the same app user is another option described in the backend reference.

```mermaid
%%{init: {"theme":"base","htmlLabels":false,"flowchart":{"wrappingWidth":240},"themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#EEF4FF","primaryTextColor":"#172033","primaryBorderColor":"#2F63E8","lineColor":"#526078","clusterBkg":"#F7F9FD","clusterBorder":"#B9C9E7"}}}%%
sequenceDiagram
    autonumber
    participant A as Android APK
    participant W as System browser
    participant B as Your backend
    participant E as EverMe
    A->>B: Start attempt with app login and secret hash
    B-->>A: Authorization URL with state and PKCE
    A->>W: Open authorization URL
    W->>E: User signs in and consents
    E-->>W: Redirect with authorization code
    W->>B: HTTPS callback with code and state
    B->>B: Validate state, attempt binding and expiry
    B->>E: Exchange code using PKCE verifier
    E-->>B: Grant and actual scopes
    Note over B: Keep grant pending, no memory access
    B-->>W: Verified App Link with one-time handle
    W-->>A: Deliver completion handle
    A->>B: Complete with login, attempt secret and handle
    B->>B: Validate and activate once
    B-->>A: Connected status and permitted capabilities
```

The backend generates an independent, unpredictable completion handle; status polling cannot obtain it. An APK without the original attempt secret cannot complete the binding. EverMe tokens and the PKCE verifier stay on the backend. Forwarding an authorization URL to someone else must not connect their memory to the sender's app account.

After activation, use `initialize → notifications/initialized → tools/list → tools/call`. Read the remote tool schemas before calling them; support JSON and SSE responses. Preserve unknown outcomes after a write or refresh timeout rather than blindly replaying the request.

Implementation references: [OAuth and MCP](../skills/apk-everme-oauth/references/oauth-mcp.md), [APK/backend responsibilities](../skills/apk-everme-oauth/references/android-backend.md), [acceptance scenarios](../skills/apk-everme-oauth/references/acceptance.md).

## 4. Give memory a clear job

Use memory to recall relevant preferences and earlier decisions. Reuse relevant context already available in this turn; search with a short topic only when history can help. Prefer the user's current statement over conflicting older memory, and preserve uncertainty. If the service is unavailable, continue the app's existing behavior without inventing recalled facts. Keep live device readings and authoritative business records in their existing systems. The following product loop adapts the official memory workflow to an app with explicit data-sharing choices.

```mermaid
%%{init: {"theme":"base","htmlLabels":false,"flowchart":{"wrappingWidth":240},"themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#EEF4FF","primaryTextColor":"#172033","primaryBorderColor":"#2F63E8","lineColor":"#526078","clusterBkg":"#F7F9FD","clusterBorder":"#B9C9E7"}}}%%
flowchart TB
    Q["User asks a question"] --> R["Reuse relevant context<br/>Search only when needed"]
    R --> A["Answer using current input<br/>and bounded memory context"]
    A --> P{"Is saving this content permitted?"}
    P -->|No| L["Continue without a cloud write"]
    P -->|Yes| S["Save a fact or conversation<br/>using the appropriate API"]
    S --> K["Inspect the receipt<br/>Accepted does not prove recallability"]
    K --> V["Verify extraction where applicable<br/>and later retrieval separately"]
    classDef component fill:#EEF4FF,stroke:#2F63E8,color:#172033
    classDef step fill:#FFF1E8,stroke:#E64A19,color:#172033
    class Q,L component
    class R,A,P,S,K,V step
```

| Task | AIUI / EverOS v2 | APK / hosted EverMe MCP |
| --- | --- | --- |
| Read relevant history | `memory/search`; request profiles when needed | `mem_search`; `mem_context` reads persistent Profile, usually once per session |
| Remember an explicit preference | Submit permitted messages with `memory/add` | Prefer `mem_save_fact` |
| Save a conversation | `memory/add` with valid messages and sender identities | `mem_save_turn`; preserve real tool-call relationships where supported |
| Request extraction | `memory/flush` after prior work has reached the processing pipeline | Use the tool's supported `flush` parameter; inspect its actual receipt |

These are conceptual counterparts, **not interchangeable payloads**. Discover EverMe's authenticated schema. A successful `mem_save_turn` receipt does not prove Profile was updated. A write accepted by either service does not prove later retrieval will find it. Treat retrieved memory as background data, not instructions that can change permissions or endpoints.

## 5. Try the skills in your project

```sh
git clone https://github.com/EasonZhu1997/Eason-Agent-Skills.git
```

Copy the **whole** selected directory, `skills/aiui-everos-direct` or `skills/apk-everme-oauth`, into the skill location supported by your coding assistant. Alternatively, ask the assistant to read that directory's `SKILL.md` directly. Both language guides use the same skill identifiers; the canonical entrypoints and detailed references remain shared.

Give the assistant your project path, target SDK/firmware, selected service and existing login/backend design. Provide credentials through secure local configuration rather than chat or repository files.

**AIUI kickoff prompt**

```text
Use $aiui-everos-direct to add EverOS memory to my AIUI project.
Read docs/rokid-memory-skills.en.md and respond in English.
Inspect the current host APIs and confirm Cloud or self-hosted v2.
Implement one recall → reply → permitted save loop without an APK relay.
Reuse the bundled JavaScript SDK; write only the app-specific wiring.
Keep shared credentials server-side and preserve user isolation.
Run the relevant local checks and list remaining service/device tests.
```

**Android kickoff prompt**

```text
Use $apk-everme-oauth to add EverMe to my Android companion app for Rokid.
Read docs/rokid-memory-skills.en.md and respond in English.
Reuse the app's login and backend. Check callback/client-name onboarding,
implement browser authorization with PKCE and initiating-app return binding,
discover MCP tools, and handle refresh, disconnect and account switching.
Complete local implementation and tests first; report live checks separately.
```

If you copied only a skill folder, supply this guide's GitHub URL instead of the `docs/` path in the prompt.

| Milestone | Evidence to collect |
| --- | --- |
| Local implementation | Reproducible tests; correct owner isolation and error states |
| Authorized service trial | Correct account, granted scopes, backend receipts, and retrieval in a new session without the original chat context |
| App and glasses trial | Exact AIX/APK build, firmware/model, observed voice and display behavior |

The SDK can be checked from the repository root with `node --test skills/aiui-everos-direct/scripts/*.test.mjs`. These are offline tests, not proof of a working glasses integration. See [validation history](validation.md).

## 6. Reference project: AIUI Sport

[Eason's AIUI-Sports-Agents](https://github.com/EasonZhu1997/AIUI-Sports-Agents) provides public Run, Bike and Rower source projects. Use the running app's existing memory boundary as a concrete place to understand SDK integration:

```mermaid
%%{init: {"theme":"base","htmlLabels":false,"flowchart":{"wrappingWidth":240},"themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#EEF4FF","primaryTextColor":"#172033","primaryBorderColor":"#2F63E8","lineColor":"#526078"}}}%%
flowchart TB
    A["AIUI Sport running app<br/>Existing coach and local records"]
    B["Application memory adapter<br/>Keep the app's result shape"]
    C["Reusable EverOS SDK<br/>add / search / flush"]
    D["Your authenticated gateway<br/>EverOS Cloud or self-hosting"]
    A -->|Existing recall and save boundary| B
    B -.->|Proposed integration| C
    C -->|HTTPS through wx.request| D
    classDef component fill:#EEF4FF,stroke:#2F63E8,color:#172033
    classDef step fill:#FFF1E8,stroke:#E64A19,color:#172033
    class A,C,D component
    class B step
```

| Public code, pinned to the reviewed version | What to learn |
| --- | --- |
| [Run / Bike / Rower projects](https://github.com/EasonZhu1997/AIUI-Sports-Agents/tree/1f34da442a830cfa571881cd6d81cb4eee08cc84/apps) | Separate AIUI apps and their lifecycle structure |
| [Running app memory boundary](https://github.com/EasonZhu1997/AIUI-Sports-Agents/blob/1f34da442a830cfa571881cd6d81cb4eee08cc84/apps/smartrun/lib/coach_api.js#L175) | Request construction, bounded `{memories, profile}` parsing and question augmentation |
| [Upload queue](https://github.com/EasonZhu1997/AIUI-Sports-Agents/blob/1f34da442a830cfa571881cd6d81cb4eee08cc84/apps/smartrun/lib/aiui_record_upload.js#L13) | FIFO processing, owner checks and deletion only after an explicit acknowledgement |

The dashed edge is a proposed SDK adaptation. The public snapshot uses its own `memory-context` / `aiui-record` backend contract and has not been migrated to this SDK. Translate EverOS results in the application adapter, preserve the original owner checks and queue rules, and validate the resulting app separately. This source example makes the integration point inspectable without claiming a live EverMind deployment.

## Sources and scope

Checked on **2026-10-24**. This is community-authored guidance for Rokid integration. Read the upstream material for its own deployment and transport; do not turn desktop-plugin installation or automatic capture behavior into APK user consent.

The guide draws on these actual official Skills, with source versions pinned for review:

| Official Skill | What this guide adapts |
| --- | --- |
| [EverOS search](https://github.com/EverMind-AI/Plugins/blob/3318dc1a2afcef3d3d804963941e8ce0bf9a3879/claude-code/skills/search/SKILL.md) | Clear recall triggers, consistent user identity and honest handling of no results |
| [EverOS status](https://github.com/EverMind-AI/Plugins/blob/3318dc1a2afcef3d3d804963941e8ce0bf9a3879/claude-code/skills/status/SKILL.md) | Check service reachability, identity and configuration before diagnosing a failure |
| [EverMe memory-mcp](https://github.com/EverMind-AI/EverMe/blob/38afee5c89aad59f3c964fa861fc8fc6d003084a/plugins/memory-mcp/SKILL.md) | Explain each memory tool by the task it serves; verify the hosted service's actual schema |
| [EverMe memory-tools](https://github.com/EverMind-AI/EverMe/blob/38afee5c89aad59f3c964fa861fc8fc6d003084a/plugins/claude-code/skills/memory-tools.md) | Reuse existing recall, keep queries focused and distinguish persistence outcomes |

Their desktop hooks, loopback services and automatic capture mechanisms are specific to those plugins. The official EverMe plugin variants also differ in tools and capture behavior; the hosted route here follows the OAuth manual and authenticated `tools/list`. Our two integration skills are development instructions; they are distinct from an EverOS `agent_skill` extracted from an agent's execution history.

- [EverOS source and deployment references](../skills/aiui-everos-direct/references/versions-and-sources.md)
- [EverMe source, hosted OAuth manual and contract differences](../skills/apk-everme-oauth/references/sources.md)

The original guidance and diagrams in this repository use the MIT license; upstream projects and documents retain their own licenses. No Rokid or EverMind certification is implied. Actual OAuth, cloud-memory operations and physical-device behavior require separate validation.

*Diagram design acknowledgment: 感谢 成都常顺鑫。*
