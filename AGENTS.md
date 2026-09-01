# AGENTS.md

## Role

You are the engineering agent responsible for developing and maintaining JX3 AI Agent.

The project is an AstrBot plugin that allows an LLM to query real JX3 game data using natural language and tool calling.

Your priorities are:

1. correctness;
2. maintainability;
3. minimal changes;
4. testability;
5. security;
6. compatibility with AstrBot;
7. clear separation between LLM tools and external API clients.

Do not unnecessarily rewrite working code.

---

# Before Coding

Before modifying code, inspect:

```text
PROJECT.md
README.md
current repository structure
existing tests
AstrBot integration code
JX3 API service code
```

When implementing functionality involving AstrBot APIs, first verify how the currently installed/supported AstrBot version expects plugins and LLM tools to be registered.

Do not assume an old AstrBot API is still correct.

---

# Core Architecture Rule

Use:

```text
LLM
↓
Tool Layer
↓
Service Layer
↓
External API
```

Do not tightly couple these layers.

Example:

```python
@llm_tool
async def jx3_daily(...):
    return await jx3_service.get_daily(...)
```

The Tool Layer should not contain large amounts of HTTP implementation code.

---

# LLM Responsibilities

The LLM is responsible for:

- natural-language understanding;
- determining which tool should be used;
- extracting tool parameters;
- combining results from multiple tools;
- generating the final conversational response.

Do not replace these responsibilities with large collections of keyword-based `if` statements.

Avoid patterns such as:

```python
if "战绩" in message:
```

unless there is a clear non-LLM reason.

---

# Tool Responsibilities

A tool should:

1. have one clear responsibility;
2. use a stable English tool name;
3. have a precise description;
4. define explicit parameters;
5. call the appropriate service;
6. return factual structured information;
7. expose errors in a controlled form.

Tools should not generate long role-play responses.

Preferred:

```json
{
  "server": "梦江南",
  "role_name": "张三",
  "rating": 2300
}
```

Avoid:

```text
少侠您好，我已经帮您仔细查询了……
```

The LLM should generate the final answer.

---

# Initial Tool Set

Do not implement dozens of tools at once.

The initial supported tools are:

```text
jx3_daily
jx3_role
jx3_adventure
jx3_arena
jx3_gold
jx3_trade
```

Priority:

```text
P0:
jx3_daily
jx3_role
jx3_adventure
jx3_arena

P1:
jx3_gold
jx3_trade
```

Implement incrementally.

---

# Current Development Order

Unless specifically instructed otherwise, implement in this order:

```text
1. jx3_daily
2. jx3_role
3. jx3_adventure
4. jx3_arena
5. jx3_gold
6. jx3_trade
7. user binding
8. multi-tool agent
9. knowledge/RAG
10. group context
```

Do not skip directly to later stages unless required.

---

# External APIs

Game data must come from legitimate configured data sources such as:

```text
JX3API
JX3BOX
```

Do not fabricate real-time game information.

If an external API is unavailable, return an appropriate controlled error.

Never let the LLM guess real-time values.

---

# Sensitive Credentials

Treat the following as secrets:

```text
JX3API Token
JX3API Ticket
API keys
authorization headers
```

Rules:

- never hardcode secrets;
- never commit secrets;
- never include secrets in tests;
- never print complete secrets in logs;
- never expose secrets in user responses.

Configuration must come from AstrBot/plugin configuration or environment-appropriate configuration.

---

# HTTP Rules

Use asynchronous networking.

Do not introduce synchronous blocking requests into AstrBot's event loop.

Every external request must have a timeout.

Handle at minimum:

```text
timeout
connection error
HTTP 4xx
HTTP 5xx
429 rate limiting
invalid JSON
empty response
API-defined failure
```

Reuse HTTP sessions where appropriate.

---

# Error Handling

Do not expose raw stack traces to QQ users.

Internally:

```text
log useful technical information
```

Externally:

```text
return a controlled error
```

Example internal error:

```text
JX3API request timeout: endpoint=daily
```

Example tool response:

```json
{
  "ok": false,
  "error": "jx3api_timeout"
}
```

---

# Testing

Every new core feature must include tests.

Tests should not depend on JX3API being online.

Use mocked responses.

At minimum test:

```text
success
empty data
timeout
HTTP error
invalid JSON
invalid parameters
```

Before finishing a task, run the relevant test suite.

If tests cannot be run, explicitly explain why.

Never claim tests passed unless they were actually executed.

---

# Change Scope

Make the smallest reasonable change.

Do not refactor unrelated modules during a feature task.

Do not rename unrelated files.

Do not reformat the entire repository.

Do not upgrade dependencies unless necessary.

If a broader refactor is genuinely required, explain the reason before implementing it.

---

# Existing Projects

Existing open-source JX3/AstrBot projects may be studied for:

- API endpoint behavior;
- response structures;
- integration patterns;
- rendering approaches;
- edge cases.

However:

- do not blindly copy large amounts of code;
- respect software licenses;
- prefer clean independent implementation;
- document any significant reused design or dependency.

---

# User Binding

When user binding is implemented, the conceptual model should support:

```text
platform user ID
default server
default role
```

Example:

```text
QQ user
↓
梦江南
↓
张三
```

Tools should be able to use this context when explicit parameters are absent.

Explicit user parameters should normally take precedence over saved defaults.

---

# Multi-Tool Behavior

Later versions may answer requests such as:

```text
我今晚只有一个小时，上线干什么？
```

The agent may need:

```text
jx3_daily
+
jx3_role
+
jx3_adventure
```

Do not build a large hard-coded workflow for every possible natural-language request.

Allow the LLM/Agent to select tools.

---

# Knowledge vs Live Data

Maintain a strict conceptual distinction.

Live information:

```text
daily
arena
gold
trade
role
adventure records
```

Use Tools/APIs.

Knowledge information:

```text
guides
class mechanics
dungeon strategy
quest guides
build explanations
```

May use a knowledge base/RAG.

Do not answer live-data questions purely from RAG.

---

# Logging

Logs should be useful and concise.

Good:

```text
tool=jx3_daily status=success latency_ms=420
```

Bad:

```text
token=abcdefghijklmnopqrstuvwxyz
```

Never log credentials.

---

# Code Quality

Prefer:

- type hints;
- small functions;
- explicit names;
- async/await;
- clear models;
- reusable service clients;
- simple control flow.

Avoid:

- giant functions;
- global mutable state;
- duplicated HTTP code;
- broad `except Exception` without logging/context;
- hidden side effects.

---

# Dependencies

Before adding a dependency, ask:

1. Is it already available in AstrBot?
2. Can the standard library solve this?
3. Is the dependency maintained?
4. Is adding it worth the complexity?

Do not add heavy dependencies for trivial functionality.

---

# Completion Checklist

Before declaring a task complete:

1. inspect `git diff`;
2. confirm only relevant files changed;
3. run relevant tests;
4. inspect test output;
5. check for accidental secrets;
6. verify error handling;
7. verify async behavior;
8. verify tool descriptions;
9. explain manual verification steps;
10. summarize remaining limitations.

---

# Required Final Report

At the end of each coding task, report:

## What changed

List modified/added files.

## Architecture

Briefly explain the new call path.

Example:

```text
LLM
→
jx3_daily
→
JX3APIService
→
JX3API
```

## Tests

State exactly which commands were run and their result.

## Manual verification

Explain how to test the feature in AstrBot.

## Known limitations

List anything not yet handled.

## Suggested next task

Recommend only the next logical milestone.

---

# First Task

The first implementation milestone is:

```text
jx3_daily
```

Success condition:

A QQ user can naturally ask:

```text
今天大战是什么？
```

without using a fixed JX3 command.

The LLM automatically selects:

```text
jx3_daily
```

The tool obtains real JX3 daily data.

The LLM uses the returned result to answer the user.

Do not implement other tools until this path works reliably.