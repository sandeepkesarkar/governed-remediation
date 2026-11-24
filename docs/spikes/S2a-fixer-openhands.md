# Spike S2a: OpenHands as the fixer, headless in Docker

| | |
|---|---|
| Date | 2026-11-24 |
| Time spent | One session, inside the timebox |
| Result | Partly |

## Question

Does the OpenHands SDK, headless in Docker with an Anthropic key, fix the login SQL injection in a local copy and add a test? What does it cost in tokens?

**Scope of this run.** The owner narrowed the spike to mechanics: how OpenHands is invoked, what it reports about cost, and whether it has a native cap. The task was a synthetic bug in a throwaway scratch file (`calc.py`), not the real login SQL injection. So the fix-the-real-flaw part of the question is **not answered**. That is why the result is "Partly". The mechanics questions are answered below.

## What we did

- Ran the OpenHands agent-server image `ghcr.io/openhands/agent-server:1.63.1-python` (index digest `sha256:506c2e243dcc3f5092ad0909c5dff9fef621298faed9042b5d4b0375fac837a5`, native `linux/arm64`, 5.5 GB). This is the sandbox.
- Drove it from a second container: `python:3.13.18-slim` with `openhands-sdk==1.63.1` and `openhands-tools==1.63.1`, using `RemoteWorkspace`. This is the client. Code is in `spikes/S2a/` (`run.sh`, `client/run.py`).
- Seeded two files inside the sandbox: `calc.py` (`add` returns `a - b`) and `test_calc.py`. Asked the agent to fix the bug, add one test case and run the test.
- Model: `anthropic/claude-sonnet-5-5` (Claude Sonnet 5.5). Caps for the real run: `max_budget_per_run=1.00`, `max_iteration_per_run=20`, wall-clock 600 s.
- Ran a second, tiny run with `max_budget_per_run=0.005` to prove the native cap stops a run.
- Watched both runs live. Neither came near a cap or the timeout.

Two failed attempts before the good run cost nothing, because they failed before any model call:

1. Client SDK was 1.49.1 against tools 1.63.1 (my two separate `pip install` calls). Fix: install both pinned together.
2. The server bound to `127.0.0.1` inside its own container, so the client could not reach it. Fix: start it with `--host 0.0.0.0`. This is container-internal. No port is published to the Mac.

## What happened

### 1. How is OpenHands invoked headless, in Docker, sandboxed?

Two containers on a private, labelled Docker network `s2a-net`:

| | Sandbox (agent-server) | Client |
|---|---|---|
| Image | `ghcr.io/openhands/agent-server:1.63.1-python@sha256:506c…37a5` | `python:3.13.18-slim@sha256:7249…ce50` plus pinned SDK |
| Does | Runs the agent, its terminal and file editor, and makes the model calls | Creates the conversation, sends the task, reads results |
| Mounts | **None** | SDK and script, read-only. An output folder. No repo, no home folder. |
| Published ports | **None** (`8000/tcp` is not mapped) | None |
| Secrets in env | None (checked: no AWS, Anthropic, GitHub, key or token variable names) | Only `ANTHROPIC_API_KEY`, passed by name so it never shows on a command line |
| Label | `project=governed-remediation` (confirmed with `docker inspect`) | Same |
| Other | Not privileged, `--cap-drop ALL`, `no-new-privileges`, 2 GB memory, 512 processes, runs as user `openhands` | |

- The sandbox's files are its own filesystem. `/Users` does not exist in it. The scratch files were created inside it with `docker exec`.
- The API key is sent from the client to the server in the conversation request. It is not in the server's environment. It is in the server's memory while a conversation runs. **Risk:** the agent runs in the same container, so treat the key as reachable by the agent. Use a key with a spending limit.
- The sandbox has normal outbound network access, because it must reach the model API. We did not restrict it to one host. That is a follow-up (see below).
- The image tag `1.63.1-python` is a real release tag. There is no `latest` anywhere. Latest SDK on PyPI at the time was 1.63.1 (2026-11-20).
- The agent-server is a compiled program. You cannot import the SDK from inside it. That is why the client is a separate container.
- I did not use the unsandboxed local runtime, and I did not mount the Docker socket. The SDK's `DockerWorkspace` helper needs the socket, so I avoided it.

### 2. Does OpenHands report cost and token usage natively?

Yes. Through the SDK, not stdout.

`conversation.conversation_stats.get_combined_metrics()` returns a metrics object with `accumulated_cost` (dollars) and `accumulated_token_usage`. Real output from the good run:

```json
{
  "status": "ConversationExecutionStatus.FINISHED",
  "seconds": 4.3,
  "model": "anthropic/claude-sonnet-5-5",
  "accumulated_cost": 0.0303965,
  "accumulated_token_usage": {
    "prompt_tokens": 20026,
    "completion_tokens": 385,
    "cache_read_tokens": 9750,
    "cache_write_tokens": 10039,
    "reasoning_tokens": 0
  }
}
```

Notes:

- Cost comes from the LiteLLM price table inside the SDK. `claude-sonnet-5-5` is in that table, so the cost is not zero. A model missing from the table would report $0. The LLM object has `input_cost_per_token` and `output_cost_per_token` overrides for that case.
- In remote mode the per-call list (`metrics.costs`) came back **empty**. Only the running total is available. That is enough for a cap. It is not enough for a per-step cost log.
- The full event stream (every action and observation) is available through a callback. I saved it as `spikes/S2a/out-run1/events.jsonl`. I searched the saved files for the key prefix and found none.
- The `openhands --headless --json` command-line tool is a separate product. I did not run it.

### 3. Is there a native budget cap and iteration cap?

Yes, both. They are arguments to `Conversation(...)`:

| Setting | What it does | Default |
|---|---|---|
| `max_budget_per_run` | Dollar cap on accumulated LLM cost. `None` means unlimited. | `None` |
| `max_iteration_per_run` | Maximum agent steps in one run. | 500 |
| `stuck_detection` | Stops a looping agent. | on |

**Proved in remote mode.** With `max_budget_per_run=0.005`, the run stopped after two steps with:

```
ConversationRunError: ... MaxBudgetReached: Agent reached maximum budget limit ($0.0050); accumulated cost $0.0052.
```

- The check runs after each step. A run can **overshoot by up to one model call**. Here it was $0.0002. A single call on a large context could be more. Set the cap below the hard ceiling.
- A hit cap raises an exception on the client. M2-7 must catch `ConversationRunError` and treat it as "budget stopped", not a crash.
- The default of 500 iterations is too high for our purposes. Set it low.
- The cap is on one conversation's accumulated cost. See "What 'three parallel fixes' means" below for how it behaves with several fixes.

### What "three parallel fixes" means (follow-up, answered from source, no paid call)

I wrote "build only a total across the three parallel fixes". That line was ambiguous. Here is what it means.

**1. It is our design, not OpenHands behaviour.** "Three at a time" comes from the HLD (section 3 step 3 and the order-and-concurrency line: "at most three fixes in progress"). It means *we* start three separate fixer conversations at once, one per finding. In the mode we used, OpenHands runs **one agent per conversation**, working one step at a time. It does not try several attempts at the same task. Evidence:

- The agent in our run was given four tools: `terminal`, `file_editor`, `task_tracker`, `finish` (read from the saved `SystemPromptEvent` in `spikes/S2a/out-run1/events.jsonl`). It used `terminal` and `finish`.
- The sub-agent tool (`TaskToolSet`) is only added when `enable_sub_agents=True`. The default is `False` (`openhands/tools/preset/default.py`, `get_default_tools`). We did not turn it on.

**2. One thing in OpenHands can start parallel workers: sub-agents. We do not use it, and M2-7 should keep it off.** If `enable_sub_agents=True` (or the older delegate tool, which runs up to 5 children in threads), the agent can start child conversations. The caps then behave like this, from `openhands/tools/task/manager.py` and `openhands/sdk/conversation/impl/local_conversation.py`:

| Question | Answer |
|---|---|
| Does `max_budget_per_run` apply to each child or to the total? | **Both, in a loose way.** Each child gets its **own full cap**: its definition's value, or else a copy of the parent's whole cap, not what is left of it. A child is checked against only its own cost. |
| Do child costs count toward the parent's cap? | **Only after the child finishes.** The child's cost is copied into the parent's stats in a `finally` block when the task ends. The parent's check reads those combined stats. While a child runs, the parent does not see its spend. |
| Worst case with the parent cap at $2 and three children? | A child can reach about $2 on its own, so up to about **$8** in total (parent plus three children) before the parent notices. |
| Does `max_iteration_per_run` apply to each child or to the total? | **Each child separately.** A child uses its definition's value, else the parent's value. Each has its own counter. The parent's counter does not include child steps. |

I read this from the source. I did not run a sub-agent, so it is untested. The real behaviour could differ, for example on how quickly the parent syncs. We avoid the question by not enabling sub-agents.

**3. What this means for the cap for M2-7.**

- With sub-agents off, each fixer conversation has exactly one cap and one iteration limit, and they apply to that one conversation. A run of three at a time can cost at most **3 x the per-conversation cap, plus up to one overshoot call each**. At $2 per conversation, that is about $6 for a batch of three.
- OpenHands has no cap across conversations. The daily cap and the three-at-a-time total are ours to build, as stated above. The simplest form: read `accumulated_cost` after each conversation, add it to a running total, and refuse to start the next conversation when the total plus one more per-conversation cap would pass the daily limit.
- Because conversations run at the same time, a running total read at start time can be behind. Reserve the full per-conversation cap when a conversation starts, and replace the reservation with the real cost when it ends.

**How I answered this:** from the SDK source I already had on disk and from the saved event log. No new paid call was made. Spike spend stays at about $0.036.

### 4. Which model?

**Claude Sonnet 5.5, `claude-sonnet-5-5` (LiteLLM id `anthropic/claude-sonnet-5-5`).**

**This is a choice for the owner to confirm. It is not a silent default.**

Why: the HLD calls for a "mid-tier Claude model" for the fixer. Sonnet 5.5 is the mid-tier current model. It fixed the bug in about four seconds of run time. Its price is in the SDK's table at about $2 per million input tokens and $10 per million output tokens (list prices, before caching).

Alternatives:

- Haiku 5.5 is about 20 times cheaper on input. Likely good enough for this toy task. Unproven for a real SQL injection fix.
- Opus 5.5 is the strongest and costs about twice as much per token as Sonnet 5.5. Worth testing if Sonnet 5.5 fails on the real flaw.

One run on a toy bug says nothing about quality on the real flaw. The model choice should be re-tested when we fix the real flaw.

### Result of the fix

The agent changed `a - b` to `a + b`, added `assert add(-1, 1) == 0`, ran the test, and it printed `ok`. Final files are in `spikes/S2a/out-run1/final-files.txt`.

## Cost

| Run | Cap | Tokens in / out | Cost |
|---|---|---|---|
| Fix the toy bug | $1.00, 20 steps | 20,026 / 385 (9,750 cache read, 10,039 cache write) | **$0.0304** |
| Budget-cap proof | $0.005 | not reported (run raised an error) | **$0.0052** (from the error text) |
| Two failed attempts | | | none (no model call) |
| **Total** | | | **about $0.036** |

The dollar figures are what OpenHands reported, from its price table. I did not check them against the Anthropic console. The owner should compare the console to this total. The cap the owner set was $10 per run. We were nowhere near it.

## Decision

For M2-7, **use the native OpenHands settings. Do not build a budget watchdog.**

- **Cap:** pass `max_budget_per_run` and `max_iteration_per_run` to `Conversation`. Catch `ConversationRunError` with `MaxBudgetReached` and record it as a stopped run.
- **Cost logging:** read `get_combined_metrics()` after each run and write one line per fix attempt: ticket ID, model, tokens in, tokens out, cache tokens, dollars, status, seconds. Save the event stream beside it.
- **What we still build:** a running total across all fixer conversations (the HLD's "three at a time", and the daily cap), which is ours to build because OpenHands only caps one conversation, a wall-clock timeout with `timeout` and a container kill as a backstop, and a check that the model is in the price table (fail loudly if the reported cost is exactly zero).
- **Suggested starting caps for the real flaw:** $2 per conversation and 40 steps. Well under the owner's $10. Adjust after the first real run.
- **Model:** Sonnet 5.5 for the first real attempt, subject to owner confirmation.

## Surprises and risks

- **Overshoot.** The cap is checked after a step, so it can be exceeded by one call. Affects M2-7 cap sizing.
- **No per-call costs in remote mode.** Only totals. Affects the HLD's "every step is logged and cost-capped" claim for fixer steps (HLD section on cost logging). Totals per fix are enough. Per-call is not available.
- **Key reachable by the agent.** The agent shares a container with the key's in-memory copy. Affects the safety rules for M2-7 and M3. Mitigation: a dedicated key with a low spending limit.
- **Outbound network is open.** The sandbox can reach the internet. A prompt injection in a finding could try to send data out. Affects M2-7. Follow-up: restrict egress to the model API host only.
- **The sandbox user is in the `sudo` group.** Harmless here because `no-new-privileges` and dropped capabilities are set. Worth a note.
- **Version drift.** The SDK moves fast (new release roughly every few days). Pin and record versions. Pip-installing at run time needs PyPI, so M2-7 should bake a client image instead.
- **The 5.5 GB image** is heavy for the 4 GB VM. It ran fine alone. Not tested next to Juice Shop and the scanners.
- **The real flaw is untested.** We do not know whether Sonnet 5.5 fixes the login SQL injection and keeps the app working. That is the first thing M2-7 should show.
- **The HLD says OpenHands runs from GitHub Actions.** This spike ran locally only. Not tested in Actions.

## Follow-up

- Add rows to `docs/ENVIRONMENT.md` for the two images and the two pip packages (done in this session).
- M2-7 should use `spikes/S2a/client/run.py` as the starting point and add: a baked client image, restricted egress, the per-fix cost line, and the real-flaw task.
- Owner to confirm the model (Sonnet 5.5) and the starting caps ($2, 40 steps) before M2-7 is drafted.
- Owner to compare the Anthropic console cost for 2026-11-24 with the $0.036 above.
- Possible new task: restrict the sandbox's outbound traffic to the model API only (propose as a row before starting).
