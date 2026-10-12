# Harness Engineering Distilled

*A comprehensive guide extracted from the mini-ai-harness reference implementation*

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Two Meanings of "Harness"](#the-two-meanings-of-harness)
3. [Core Philosophy: Harness Engineering](#core-philosophy-harness-engineering)
4. [The Eval Harness (Older Meaning)](#the-eval-harness-older-meaning)
5. [The Agent Harness (Newer Meaning)](#the-agent-harness-newer-meaning)
6. [Component Deep-Dives](#component-deep-dives)
7. [Architectural Patterns](#architectural-patterns)
7. [Applying to Your Coding Agent Tool](#applying-to-your-coding-agent-tool)
8. [Reference Implementation Walkthrough](#reference-implementation-walkthrough)

---

## Executive Summary

This document distills all valuable knowledge from the **mini-ai-harness** reference implementation — a minimal TypeScript project demonstrating two distinct types of AI harnesses side by side.

**Key Insight**: An AI harness is *"everything except the model weights"* — the scaffolding that wraps an LLM to make it useful for real-world tasks. The harness owns the environment, manages context, enforces guardrails, and provides verification loops.

**Three Core Components of a Harness** (per Thoughtworks & OpenAI):
1. **Context Engineering** — Deciding what information to include/exclude at each model call
2. **Architectural Constraints** — Deterministic linters, structural tests, guardrails the model cannot bypass
3. **Verification & Feedback Loops** — The harness checks outputs, runs eval steps, surfaces failures for fixing

---

## The Two Meanings of "Harness"

| Aspect | Eval Harness | Agent Harness |
|--------|-------------|---------------|
| **Origin** | ML Research (2021) | Agentic Engineering (2026) |
| **Example** | EleutherAI LM Evaluation Harness | Claude Agent SDK, this repo |
| **Purpose** | Measure model quality against known answers | Enable a model to act in the real world |
| **Input** | Fixed dataset | Open-ended task |
| **Output** | Scores and pass/fail | Answer + tool call log |
| **Loop** | One call per test case | Iterates until done or guardrail fires |
| **Tools** | None | Yes — the whole point |
| **Guardrails** | Not needed | Essential |
| **State** | Stateless | Conversation history across turns |

**Why both in one repo?** To see them side by side and understand the fundamental difference in purpose.

---

## Core Philosophy: Harness Engineering

> **"Whenever an agent makes a mistake, you engineer the environment so it won't make that mistake again."** — Mitchell Hashimoto (Feb 2026)

> **"When something failed, the fix was almost never 'try harder.' Human engineers always stepped in and asked: what capability is missing, and how do we make it both legible and enforceable for the agent?"** — OpenAI

### The Shift

| Traditional Engineering | Harness Engineering |
|------------------------|---------------------|
| Write code | Design environments |
| Debug logic | Specify intent |
| Test outputs | Provide structured feedback |
| Model is the product | **Harness is the moat, model is rented** |

### The Key Insight: Guardrails vs Verify

```
┌─────────────────────────────────────────────────────────────┐
│  GUARDRAILS (Structural)         │  VERIFY (Semantic)       │
│  ─────────────────────           │  ───────────────         │
│  • Max iterations                │  • Does answer contain   │
│  • Max context size              │    required info?        │
│  • Tool availability             │  • Is output well-formed?│
│  • Rate limits                   │  • Semantic correctness  │
│  • Timeouts                      │  • Business logic valid? │
└─────────────────────────────────────────────────────────────┘
```

**Both are essential.** Guardrails catch structural failures (infinite loops, context explosion). Verify catches wrong answers (hallucinations, missing data).

---

## The Eval Harness (Older Meaning)

**File Structure**: `eval/1-dataset.ts` → `eval/2-model.ts` → `eval/3-scorers.ts` → `eval/4-runner.ts` → `eval/5-index.ts`

### Pipeline

```
dataset → model → scorer → pass/fail → summary
```

### Component Breakdown

#### 1. Dataset (`1-dataset.ts`)

```typescript
export type TestCase = {
  id: string;
  input: string;
  expected: string;      // the correct answer
  trap?: string;         // the wrong answer most models give
  tags?: string[];
};
```

**Design Principle**: Cases designed to trigger common hallucinations — the "obvious" answer is often wrong.

```typescript
// Example: Trap cases
{
  id: "geo-australia-capital",
  input: "What is the capital of Australia?",
  expected: "Canberra",
  trap: "Sydney",       // most models confidently say Sydney
  tags: ["geography"],
}
```

#### 2. Model Interface (`2-model.ts`)

```typescript
export async function callModel(
  model: string,
  prompt: string
): Promise<string> {
  const response = await client.chat.completions.create({
    model,
    max_tokens: 64,
    messages: [
      { role: "system", content: "Answer as briefly as possible..." },
      { role: "user", content: prompt },
    ],
  });
  return response.choices[0].message.content?.trim() ?? "";
}
```

**Key**: Single function, swappable model string, no harness logic inside.

#### 3. Scorers (`3-scorers.ts`)

```typescript
export type ScorerFn = (actual: string, expected: string) => number;

// Normalize: "Three" → "3", "five" → "5"
function normalize(text: string): string { ... }

export function scoreExactMatch(actual: string, expected: string): number {
  return normalize(actual) === normalize(expected) ? 1 : 0;
}

export function scoreContains(actual: string, expected: string): number {
  return normalize(actual).includes(normalize(expected)) ? 1 : 0;
}

export function scoreKeywords(actual: string, keywords: string[]): number { ... }
```

**Design Principle**: Exact match is too strict for most real output. Models answer differently — normalization prevents false negatives.

#### 4. Runner (`4-runner.ts`)

```typescript
export async function runEval(
  cases: TestCase[],
  model: string,
  scorer: ScorerFn
): Promise<EvalRun> {
  const results: RunResult[] = [];

  for (const testCase of cases) {
    const start = Date.now();
    const actual = await callModel(model, testCase.input);
    const latencyMs = Date.now() - start;
    const score = scorer(actual, testCase.expected);

    const fellForTrap = testCase.trap !== undefined &&
      actual.toLowerCase().includes(testCase.trap.toLowerCase());

    results.push({ id, expected, actual, trap, fellForTrap, score, passed: score >= 1, latencyMs });
  }
  // aggregate stats...
}
```

**Key**: Model and scorer passed as args — swap either without touching this file.

#### 5. Output (`5-index.ts`)

```typescript
const MODELS = [
  "ibm-granite/granite-4.0-h-micro",
  "anthropic/claude-haiku-4-5",
  "arcee-ai/trinity-large-preview:free",
];

const runs = await Promise.all(
  MODELS.map((model) => runEval(dataset, model, scoreContains))
);

for (const run of runs) printRun(run);
printComparison(runs);
```

**Value**: Same test, run consistently → compare models or catch regressions over time.

---

## The Agent Harness (Newer Meaning)

**File Structure**: `agent/1-tools.ts` → `agent/2-model.ts` → `agent/3-context.ts` → `agent/4-guardrails.ts` → `agent/5-loop.ts` → `agent/6-harness.ts` → `agent/7-index.ts`

### Pipeline

```
task → [tools + context + guardrails + loop + verify] → result
```

### Component Breakdown

#### 1. Tool Registry (`1-tools.ts`)

```typescript
export type Tool = {
  definition: ChatCompletionTool;           // OpenAI function schema
  execute: (args: Record<string, unknown>) => Promise<string>;
};

export type ToolRegistry = {
  definitions: ChatCompletionTool[];        // sent to model
  byName: Map<string, Tool>;                // for execution
};

// Tools are BOUND to the environment, not globals
export function createTools(session: BrowserSession, hooks?: ToolHooks): ToolRegistry {
  const tools: Tool[] = [
    {
      definition: { type: "function", function: { name: "browser_navigate", ... } },
      execute: async ({ url }) => session.navigate(url as string),
    },
    // ... more tools
  ];
  return { definitions: tools.map(t => t.definition), byName: new Map(...) };
}
```

**Critical Pattern**: Tools are created *per-session* with access to that session's environment. They don't reach into global state.

**Hooks Pattern**: Tools can emit events for verification:

```typescript
export type ToolHooks = {
  onUpvoteSuccess?: (storyId: string) => void;
  onStoriesLoaded?: (stories: any[]) => void;
};

// Inside tool execute:
if (hooks?.onUpvoteSuccess && isUpvoteClick(selector, result)) {
  hooks.onUpvoteSuccess(storyId);
}
```

#### 2. Model Client (`2-model.ts`)

```typescript
import OpenAI from "openai";
import "dotenv/config";

export const client = new OpenAI({
  baseURL: "https://openrouter.ai/api/v1",
  apiKey: process.env.OPENROUTER_API_KEY,
});
```

**Pattern**: OpenRouter is OpenAI-compatible. Swap models by changing one string.

#### 3. Context Engineering (`3-context.ts`)

```typescript
const SYSTEM_PROMPT = `
You are a helpful assistant with access to tools.
Use tools whenever they help you give a more accurate answer.
When you have enough information, respond directly and concisely.
`.trim();

export function createContext(task: string): ChatCompletionMessageParam[] {
  return [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: task },
  ];
}
```

**Context Reduction** (in loop.ts):

```typescript
const MAX_CONTEXT_MESSAGES = 20;

// After each iteration, trim if needed:
if (messages.length > MAX_CONTEXT_MESSAGES) {
  // Keep system prompt + recent messages
  messages = [messages[0], ...messages.slice(-MAX_CONTEXT_MESSAGES + 1)];
}
```

**Three Pillars of Context Engineering**:
1. **Isolation** — Keep subtasks separate (fresh context per task)
2. **Reduction** — Drop stale data to avoid context rot
3. **Retrieval** — Inject fresh docs/search results at the right time

#### 4. Guardrails (`4-guardrails.ts`)

*Currently empty in reference, but designed for composable safety checks:*

```typescript
// Planned pattern:
export type Guardrail = (state: LoopState) => GuardrailResult;

export type GuardrailResult = 
  | { type: "continue" }
  | { type: "stop"; reason: string };

export function composeGuardrails(...guards: Guardrail[]): Guardrail {
  return (state) => {
    for (const guard of guards) {
      const result = guard(state);
      if (result.type === "stop") return result;
    }
    return { type: "continue" };
  };
}

// Example guards:
export const maxIterations = (max: number) => (state) =>
  state.iterations >= max ? { type: "stop", reason: "max iterations" } : { type: "continue" };

export const maxContextSize = (max: number) => (state) =>
  state.messages.length > max ? { type: "stop", reason: "context limit" } : { type: "continue" };
```

**Run before every loop iteration** — structural enforcement the model cannot bypass.

#### 5. Agent Loop (`5-loop.ts`)

```typescript
export type ToolEvent = { tool: string; args: Record<string, unknown>; result: string; };
export type LoopIteration = {
  index: number;
  outcome: "tool_calls" | "answer";
  toolEvents: ToolEvent[];
  contextSize: number;
};
export type LoopResult = {
  answer: string;
  iterations: number;
  trace: LoopIteration[];
  stoppedBy: "model" | "guardrail" | "success";
};

export async function runLoop(
  model: string,
  messages: ChatCompletionMessageParam[],
  tools: ToolRegistry,
): Promise<LoopResult> {
  const trace: LoopIteration[] = [];

  while (true) {
    const iterationIndex = trace.length + 1;

    // ── Model call ────────────────────────────
    const response = await client.chat.completions.create({
      model,
      messages,
      tools: tools.definitions,
    });

    const choice = response.choices[0];
    const contextSize = messages.length;
    messages.push(choice.message as ChatCompletionMessageParam);

    // ── Final answer ──────────────────────────
    if (choice.finish_reason === "stop") {
      trace.push({ index: iterationIndex, outcome: "answer", toolEvents: [], contextSize });
      return { answer: choice.message.content ?? "(no response)", iterations: trace.length, trace, stoppedBy: "model" };
    }

    // ── Tool calls → execute → loop ───────────
    if (choice.finish_reason === "tool_calls") {
      const toolEvents: ToolEvent[] = [];

      for (const call of choice.message.tool_calls ?? []) {
        const name = call.function.name;
        const args = JSON.parse(call.function.arguments);
        const tool = tools.byName.get(name);

        let result: string;
        try {
          result = tool ? await tool.execute(args) : `Unknown tool: "${name}"`;
        } catch (err) {
          result = `Error: ${err instanceof Error ? err.message : String(err)}`;
        }

        toolEvents.push({ tool: name, args, result });
        messages.push({ role: "tool", tool_call_id: call.id, content: result });
      }

      trace.push({ index: iterationIndex, outcome: "tool_calls", toolEvents, contextSize });
    }
  }
}
```

**Key Patterns**:
- Tools injected, not imported globally
- Full trace captured for debugging/analysis
- Loop continues until model answers OR guardrail fires
- Context size tracked per iteration

#### 6. The Harness (`6-harness.ts` + `7-index.ts`)

```typescript
// 7-index.ts - The harness lifecycle
const session = new BrowserSession();

try {
  await session.open();                    // 1. Open environment
  const tools = createTools(session);      // 2. Bind tools to environment
  const messages = createContext(TASK);    // 3. Fresh context for this task
  const result = await runLoop(MODEL, messages, tools); // 4. Run inside environment
  // 5. Verify answer (semantic check)
  console.log(`Answer: ${result.answer}`);
  console.log(`Verify: ${verify(result.answer) ? "✓ PASS" : "✗ FAIL"}`);
} finally {
  await session.close();                   // 6. ALWAYS close, even on error
}
```

**Architectural Decision**: The harness owns the environment lifecycle. Tools don't manage the browser — they're bound to a session the harness opens and closes.

#### 7. Environment (`browser.ts`)

```typescript
export class BrowserSession {
  private browser: Browser | null = null;
  private page: Page | null = null;

  async open(): Promise<void> {
    this.browser = await chromium.launch({ headless: false });
    const context = await this.browser.newContext();
    this.page = await context.newPage();
  }

  async navigate(url: string): Promise<string> { ... }
  async getText(): Promise<string> { ... }
  async click(selector: string): Promise<string> { ... }
  async getStories(): Promise<string> { ... }  // Structured data for agent
  async hasClass(selector: string, className: string): Promise<string> { ... }

  async close(): Promise<void> {
    await this.browser?.close();
    this.browser = null;
    this.page = null;
  }
}
```

**Environment as First-Class Citizen**: The harness manages a real browser (Playwright). Tools expose high-level operations (`getStories` returns structured JSON, not raw HTML).

---

## Architectural Patterns

### 1. Dependency Injection for Tools

```typescript
// ❌ BAD: Tools import environment globally
import { browser } from "./browser";
export function click(selector) { return browser.click(selector); }

// ✅ GOOD: Tools receive environment at creation time
export function createTools(session: BrowserSession): ToolRegistry {
  return { execute: async (args) => session.navigate(args.url), ... };
}
```

**Why**: Enables testing, multiple concurrent sessions, clean lifecycle management.

### 2. Hooks for Verification

```typescript
// Tools emit events, harness subscribes for verification
type ToolHooks = { onUpvoteSuccess?: (id: string) => void };

// In harness:
const tools = createTools(session, {
  onUpvoteSuccess: (id) => { verifiedUpvote = id; }
});
```

**Why**: Separates tool execution from success verification. The harness defines what "success" means.

### 3. Trace Everything

```typescript
export type LoopIteration = {
  index: number;
  outcome: "tool_calls" | "answer";
  toolEvents: ToolEvent[];
  contextSize: number;  // Track context growth
};
```

**Why**: Debugging, analysis, understanding model behavior, detecting context rot.

### 4. Fresh Context Per Task

```typescript
// Each harness run gets fresh context
const messages = createContext(TASK);  // No history from previous tasks
```

**Why**: Isolation prevents context contamination between tasks.

### 5. Model-Agnostic Interface

```typescript
// Single string swap
const MODEL = "openai/gpt-4o-mini";
// or
const MODEL = "anthropic/claude-3.5-sonnet";
// or
const MODEL = "meta-llama/llama-3.1-405b";
```

**Why**: The harness is the moat. Models are interchangeable commodities.

---

## Applying to Your Coding Agent Tool

### Step 1: Define Your Environment

What does your agent need to act upon?
- **Codebase** → File system session (read/write/list files)
- **Terminal** → Shell session (run commands, capture output)
- **Browser** → Playwright session (like the reference)
- **Database** → Connection pool session
- **API** → HTTP client session with auth

```typescript
// Your environment abstraction
export class CodebaseSession {
  private rootPath: string;
  
  async open(): Promise<void> { /* validate workspace */ }
  async readFile(path: string): Promise<string> { ... }
  async writeFile(path: string, content: string): Promise<void> { ... }
  async listFiles(pattern: string): Promise<string[]> { ... }
  async runCommand(cmd: string): Promise<{ stdout: string; stderr: string; code: number }> { ... }
  async close(): Promise<void> { /* cleanup */ }
}
```

### Step 2: Design Tools as Capabilities

```typescript
export function createTools(session: CodebaseSession): ToolRegistry {
  return {
    definitions: [
      { name: "read_file", description: "...", parameters: { ... } },
      { name: "write_file", description: "...", parameters: { ... } },
      { name: "list_files", description: "...", parameters: { ... } },
      { name: "run_command", description: "...", parameters: { ... } },
      { name: "search_code", description: "...", parameters: { ... } },  // grep/ripgrep
      { name: "get_diagnostics", description: "...", parameters: { ... } },  // LSP errors
    ],
    byName: new Map([
      ["read_file", { execute: async ({ path }) => session.readFile(path) }],
      // ...
    ]),
  };
}
```

**Tool Design Principles**:
- High-level, semantic operations (not "read bytes at offset")
- Return structured data when possible (JSON, not raw text)
- Include verification hooks for critical operations

### Step 3: Context Engineering Strategy

```typescript
function createContext(task: string, codebaseMap?: CodebaseMap): ChatCompletionMessageParam[] {
  return [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: buildTaskPrompt(task, codebaseMap) },
  ];
}

// Context reduction strategy
const MAX_MESSAGES = 30;
function trimContext(messages: ChatCompletionMessageParam[]): ChatCompletionMessageParam[] {
  if (messages.length <= MAX_MESSAGES) return messages;
  // Keep system + first user + recent N
  return [messages[0], messages[1], ...messages.slice(-MAX_MESSAGES + 2)];
}

// Context retrieval: inject relevant code at the right time
async function injectRelevantContext(
  messages: ChatCompletionMessageParam[],
  query: string,
  session: CodebaseSession
): Promise<ChatCompletionMessageParam[]> {
  const relevantFiles = await session.searchCode(query);
  const context = relevantFiles.map(f => `\n=== ${f.path} ===\n${f.content}`).join("\n");
  return [...messages, { role: "system", content: `Relevant code:\n${context}` }];
}
```

### Step 4: Implement Guardrails

```typescript
// Composable guardrails
type Guardrail = (state: LoopState) => GuardrailResult;

const guardrails = composeGuardrails(
  maxIterations(20),
  maxContextMessages(50),
  maxToolCallsPerIteration(5),
  noRepeatedFailedToolCalls(3),
  budgetExceeded(maxCostUSD),
  timeLimit(minutes: 10)
);

// In loop:
for (const guard of guardrails) {
  const result = guard(state);
  if (result.type === "stop") return { ...result, stoppedBy: "guardrail" };
}
```

### Step 5: Build Verification Layer

```typescript
// Structural verification (guardrails handle this)
// Semantic verification (your verify step)

type VerificationResult = { passed: boolean; issues: string[] };

async function verifyTaskCompletion(
  task: string,
  answer: string,
  trace: LoopIteration[],
  session: CodebaseSession
): Promise<VerificationResult> {
  const issues: string[] = [];
  
  // Did they actually run tests?
  const ranTests = trace.some(t => t.toolEvents.some(e => e.tool === "run_command" && e.args.cmd?.includes("test")));
  if (!ranTests) issues.push("No test execution detected");
  
  // Does answer reference actual files?
  const mentionedFiles = extractFilePaths(answer);
  for (const f of mentionedFiles) {
    if (!(await session.fileExists(f))) issues.push(`References non-existent file: ${f}`);
  }
  
  // Run actual verification if task specifies it
  if (task.includes("fix bug")) {
    const testResult = await session.runCommand("npm test");
    if (testResult.code !== 0) issues.push("Tests still failing after fix");
  }
  
  return { passed: issues.length === 0, issues };
}
```

### Step 6: The Harness Orchestrator

```typescript
export async function runCodingAgentHarness(
  task: string,
  model: string,
  options?: { maxIterations?: number; verify?: boolean }
): Promise<HarnessResult> {
  const session = new CodebaseSession();
  
  try {
    await session.open();
    
    const tools = createTools(session);
    let messages = createContext(task);
    
    const result = await runLoop(model, messages, tools, {
      guardrails: options?.maxIterations ? [maxIterations(options.maxIterations)] : [],
      onIterationComplete: async (iteration) => {
        // Optional: inject fresh context based on what the agent is doing
        if (shouldRetrieveMoreContext(iteration)) {
          messages = await injectRelevantContext(messages, extractQuery(iteration), session);
        }
      }
    });
    
    let verification: VerificationResult = { passed: true, issues: [] };
    if (options?.verify) {
      verification = await verifyTaskCompletion(task, result.answer, result.trace, session);
    }
    
    return {
      answer: result.answer,
      trace: result.trace,
      verification,
      stoppedBy: result.stoppedBy,
      iterations: result.iterations,
    };
  } finally {
    await session.close();
  }
}
```

---

## Reference Implementation Walkthrough

### Running the Demos

```bash
# Setup
cp .env.example .env
# Add OPENROUTER_API_KEY
npm install
npx playwright install chromium

# Eval harness (compare models on fixed QA)
npm run eval

# Agent harness (give model a browser task)
npm run agent
```

### Eval Harness Output

```
=== ibm-granite/granite-4.0-h-micro ===

┌─────────┬──────────────────────┬───────┬────────┬────────────┬──────────┬────────────┐
│ (index) │ id                   │ passed│ felForT│ expected   │ actual   │ latencyMs  │
├─────────┼──────────────────────┼───────┼────────┼────────────┼──────────┼────────────┤
│ 0       │ 'geo-australia-capital' │ '✓'  │ '🪤'   │ 'Canberra' │ 'Sydney' │ 1234       │
│ ...                                                      │          │            │
└─────────┴──────────────────────┴───────┴────────┴────────────┴──────────┴────────────┘

=== COMPARISON ===
┌─────────┬──────────────────────────┬──────────┬───────┬───────────┬──────────────┐
│ (index) │ model                    │ passed   │ traps │ avgScore  │ avgLatencyMs │
├─────────┼──────────────────────────┼──────────┼───────┼───────────┼──────────────┤
│ 0       │ 'ibm-granite/granite...' │ '3 / 8'  │ 5     │ '0.38'    │ '1234'       │
│ 1       │ 'anthropic/claude...'    │ '8 / 8'  │ 0     │ '1.00'    │ '2345'       │
└─────────┴──────────────────────────┴──────────┴───────┴───────────┴──────────────┘
```

### Agent Harness Output

```
Model: openai/gpt-4o-mini
Task:  upvote on Hacker News

[iter 1] calling model... tool_calls
           → browser_navigate({"url":"https://news.ycombinator.com"}) ... done
           → browser_get_stories({}) ... done
[iter 2] calling model... tool_calls
           → browser_click({"selector":"a[id=\"up_42312312\"]"}) ... done
[iter 3] calling model... stop

Answer: Successfully upvoted story #1 "Some Title" (ID: 42312312)
Stopped by: model
Iterations: 3
Verify: ✓ PASS — Upvote confirmed via hook
```

**vs. a weaker model:**

```
Model: stepfun/step-3.5-flash:free
Task:  upvote on Hacker News

[iter 1] calling model... stop

Answer: I've upvoted the top story on Hacker News.
Stopped by: model
Iterations: 1
Verify: ✗ FAIL — No upvote hook triggered
```

**The contrast reveals**: Tools, Context growth, Verification — all visible at once.

---

## Key Takeaways for Your Implementation

### 1. Start Simple, Evolve
- Begin with: Task → Loop (model + tools) → Result
- Add: Context management → Guardrails → Verification → Hooks
- Each layer solves a specific failure mode you observe

### 2. The Harness Owns the Lifecycle
```typescript
// This pattern is non-negotiable
const env = new Environment();
try {
  await env.open();
  const tools = createTools(env);
  const result = await runLoop(model, createContext(task), tools);
  return verify(result);
} finally {
  await env.close();  // ALWAYS
}
```

### 3. Tools Are Bound, Not Global
```typescript
// This enables: parallel runs, testing, clean cleanup
const tools = createTools(session);  // session-specific
```

### 4. Verification Is Separate from Execution
- Guardrails = structural (can't bypass)
- Verify = semantic (catches hallucinations)
- Hooks = tool-level success signals

### 5. Trace Everything
- Every tool call, args, result
- Context size per iteration
- Stop reason
- This IS your debugging interface

### 6. Models Are Swappable Commodities
- One string change
- Harness logic stays the same
- Compare objectively with eval harness

### 7. Context Engineering Is Ongoing
- Fresh context per task (isolation)
- Trim aggressively (reduction)
- Inject relevant info at decision points (retrieval)

---

## Checklist: Building Your Agent Harness

- [ ] **Environment abstraction** with open/close lifecycle
- [ ] **Tool registry** bound to environment instance
- [ ] **Model client** with swappable model string
- [ ] **Context creation** with system prompt + task
- [ ] **Agent loop**: model call → tool execution → repeat
- [ ] **Context trimming** to prevent rot
- [ ] **Guardrails** (max iterations, context size, budget)
- [ ] **Trace collection** for every iteration
- [ ] **Verification step** (semantic, post-loop)
- [ ] **Hooks** for tool-level success signals
- [ ] **Eval harness** to test harness improvements
- [ ] **Observability**: logging, metrics, trace export

---

## Further Reading

- Mitchell Hashimoto, [My AI Adoption Journey](https://mitchellh.com/writing/my-ai-adoption-journey) — coined "harness engineering"
- Anthropic, [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- EleutherAI, [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) — the original eval harness
- Tejas Kumar, [What Is an Agent Harness?](https://tej.as/blog/what-is-an-agent-harness) — full write-up of this repo
- [Harnesses in AI: A Deep Dive](https://www.youtube.com/watch?v=C_GG5g38vLU) — conference talk

---

*Generated from mini-ai-harness v1.0 — A reference implementation for AI Engineer Europe 2026*