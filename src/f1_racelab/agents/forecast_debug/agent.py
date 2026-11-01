"""A tool-using LLM agent that investigates batch-vs-live forecast discrepancies.

Protocol: every model reply is one JSON object, either an action
``{"thought": "...", "action": "<tool>", "args": {...}}`` or a final answer
``{"final": {"root_cause": "<label>", "evidence": ["t2", "t4"], "explanation": "...", "confidence": 0.7}}``.
Each tool call gets an id (``t1``, ``t2``, ...); a final answer must cite the ids it relies on, and cited ids that
were never produced are dropped, so evidence cannot be invented.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from f1_racelab.agents.forecast_debug.llm import ChatModel, extract_json
from f1_racelab.agents.forecast_debug.scenarios import DESCRIPTIONS, LABELS
from f1_racelab.agents.forecast_debug.tools import ForecastTools

QUESTION = ("Forecast consumers report that the batch (nightly) and live (on-demand) next-lap pace forecasts do not "
            "always line up, and some forecasts may be wrong. Investigate the data, models and configuration, then "
            "identify the single most likely root cause, or say there is no material discrepancy.")
OBSERVATION_CHARS = 4000


def system_prompt() -> str:
    tools = "\n".join(f"- {t['name']}({json.dumps(t['args'])}): {t['description']}" for t in ForecastTools.specs())
    labels = "\n".join(f"- {label}: {DESCRIPTIONS[label]}" for label in LABELS)
    return f"""You are a forecast-debugging agent with read-only access to a forecasting warehouse.
Investigate with tools before concluding. Base every claim on tool observations, not assumptions.
Begin with incident_checks to see coverage, model versions, feature skew, lap alignment and observed bias.
Investigate any suspicious signals with specific SQL or table inspections before assigning a cause.
Batch/live agreement does NOT prove that both models are accurate; check observed outcomes and season bias.
Do not claim no_material_discrepancy after only comparing aggregate batch/live forecasts.
The incident_checks tool returns observations, never a definitive diagnosis.

Tools:
{tools}

Root-cause labels (choose exactly one):
{labels}

Reply with ONE JSON object and nothing else:
- to use a tool: {{"thought": "why", "action": "<tool name>", "args": {{...}}}}
- to finish: {{"final": {{"root_cause": "<label>", "evidence": ["<tool ids you relied on, e.g. t3>"],
  "explanation": "what the evidence shows", "confidence": <0..1>}}}}"""


@dataclass
class Diagnosis:
    root_cause: str
    evidence: list[str]
    explanation: str
    confidence: float | None
    steps: int
    trace: list[dict[str, Any]] = field(default_factory=list)
    invalid_replies: int = 0
    tool_errors: int = 0


def run_agent(model: ChatModel, tools: ForecastTools, question: str = QUESTION, max_steps: int = 12) -> Diagnosis:
    messages = [{"role": "system", "content": system_prompt()}, {"role": "user", "content": question}]
    trace: list[dict[str, Any]] = []
    produced: set[str] = set()
    invalid = errors = 0
    for step in range(1, max_steps + 1):
        reply = model.complete(messages)
        messages.append({"role": "assistant", "content": reply})
        parsed = extract_json(reply)
        if parsed is not None and isinstance(parsed.get("final"), dict):
            final = parsed["final"]
            label = str(final.get("root_cause", ""))
            cited = [str(e) for e in final.get("evidence", []) if isinstance(e, str | int)]
            trace.append({"step": step, "final": final})
            confidence = final.get("confidence")
            return Diagnosis(
                root_cause=label if label in LABELS else "invalid_label",
                evidence=[e for e in cited if e in produced],
                explanation=str(final.get("explanation", "")),
                confidence=float(confidence) if isinstance(confidence, int | float) else None,
                steps=step, trace=trace, invalid_replies=invalid, tool_errors=errors)
        if parsed is None or not isinstance(parsed.get("action"), str):
            invalid += 1
            trace.append({"step": step, "invalid_reply": reply[:500]})
            messages.append({"role": "user", "content": "Invalid reply. Answer with exactly one JSON object: "
                                                        "an action or a final answer."})
            continue
        tool_id = f"t{len(produced) + 1}"
        produced.add(tool_id)
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        observation = tools.call(parsed["action"], args)
        if "error" in observation:
            errors += 1
        text = json.dumps(observation, default=str)
        if len(text) > OBSERVATION_CHARS:
            text = text[:OBSERVATION_CHARS] + "...(truncated; narrow the query)"
        trace.append({"step": step, "tool_id": tool_id, "action": parsed["action"], "args": args,
                      "thought": parsed.get("thought"), "observation": text})
        messages.append({"role": "user", "content": f"Observation {tool_id}: {text}"})
    return Diagnosis(root_cause="undetermined", evidence=[], explanation="step budget exhausted", confidence=None,
                     steps=max_steps, trace=trace, invalid_replies=invalid, tool_errors=errors)
