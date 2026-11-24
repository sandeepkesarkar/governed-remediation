"""S2a spike client. Throwaway. Drives the OpenHands agent-server container over HTTP.

Reads: AGENT_HOST, ANTHROPIC_API_KEY (env), MODEL, MAX_BUDGET, MAX_ITER.
Writes to /out: events.jsonl, metrics.json.
Never prints the API key.
"""
import json, os, sys, time
from pydantic import SecretStr
from openhands.sdk import LLM, Conversation
from openhands.sdk.workspace import RemoteWorkspace
from openhands.tools.preset.default import get_default_agent

host = os.environ["AGENT_HOST"]
model = os.environ["MODEL"]
budget = float(os.environ["MAX_BUDGET"])
max_iter = int(os.environ["MAX_ITER"])

llm = LLM(model=model, api_key=SecretStr(os.environ["ANTHROPIC_API_KEY"]), usage_id="s2a")
agent = get_default_agent(llm=llm, cli_mode=True)  # cli_mode: no browser tool
ws = RemoteWorkspace(host=host, working_dir="/workspace/scratch")

evf = open("/out/events.jsonl", "w")
def on_event(ev):
    evf.write(ev.model_dump_json() + "\n"); evf.flush()
    print("EVENT", type(ev).__name__, flush=True)

conv = Conversation(agent=agent, workspace=ws, callbacks=[on_event],
                    max_iteration_per_run=max_iter, max_budget_per_run=budget)
conv.send_message(
    "In this directory, calc.py has a bug and test_calc.py fails. "
    "Fix the bug in calc.py, add one more test case to test_calc.py, and run "
    "`python test_calc.py` to confirm it passes. Keep it minimal.")
t0 = time.time()
conv.run()
secs = time.time() - t0
m = conv.conversation_stats.get_combined_metrics()
snap = m.get_snapshot() if hasattr(m, "get_snapshot") else None
out = {
    "status": str(conv.state.execution_status),
    "seconds": round(secs, 1),
    "model": model,
    "max_budget_per_run": budget,
    "max_iteration_per_run": max_iter,
    "accumulated_cost": m.accumulated_cost,
    "accumulated_token_usage": m.accumulated_token_usage.model_dump() if m.accumulated_token_usage else None,
    "n_llm_calls": len(m.costs),
    "per_call_costs": [c.cost for c in m.costs],
}
json.dump(out, open("/out/metrics.json", "w"), indent=2)
print("METRICS", json.dumps(out))
conv.close()
