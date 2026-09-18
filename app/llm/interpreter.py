"""LLM interpreter for operator notes. Owner: Turjo (reliability pass: Samprity).

Design: the language model does *language only*. It returns, per note, a directive type, one or
more whole-hour windows (start inclusive, end exclusive) and a typed value. Deterministic code in
app/directives.py expands windows into the `hours` array and converts percentages into kWh, so the
model never does arithmetic that the judge checks.

Providers are OpenAI-compatible chat endpoints (OpenAI, Groq). Output is constrained with a JSON
schema where the provider supports it (falling back to json_object), and every request runs under
one overall deadline so the judge's 30 s limit can never be exceeded by a slow provider chain.
"""
import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx

from app.schemas import Battery

logger = logging.getLogger("gridwise.llm")

DIRECTIVE_TYPES = [
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]
VALUE_KINDS = ["none", "usable_solar_fraction", "reserve_kwh", "reserve_percent_of_capacity", "max_grid_kwh"]

# Strict JSON schema (every property required, no extras) — accepted by OpenAI strict mode and
# Groq's json_schema mode. Nullable fields are avoided so the same schema works on both.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "interpretations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "note_index": {"type": "integer"},
                    "directive_type": {"type": "string", "enum": DIRECTIVE_TYPES},
                    "windows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "start_hour": {"type": "integer"},
                                "end_hour_exclusive": {"type": "integer"},
                            },
                            "required": ["start_hour", "end_hour_exclusive"],
                        },
                    },
                    "value_kind": {"type": "string", "enum": VALUE_KINDS},
                    "value": {"type": "number"},
                    "explanation": {"type": "string"},
                },
                "required": ["note_index", "directive_type", "windows", "value_kind", "value", "explanation"],
            },
        }
    },
    "required": ["interpretations"],
}

SYSTEM_PROMPT = """You interpret short operator notes for a campus energy scheduler. The schedule covers TODAY, hours 0-23.
For EVERY note (indexed 0..N-1) return exactly one interpretation object. Never skip or merge notes.

DIRECTIVE TYPES (choose exactly one per note):
- solar_reduction: usable rooftop solar is reduced for some hours (cleaning, cloud, inverter work, shading, maintenance).
  value_kind = "usable_solar_fraction", value = the FRACTION OF NORMAL OUTPUT THAT REMAINS, 0..1.
    "drops to about 20%" / "one-fifth of normal" / "roughly a quarter" -> 0.2 / 0.2 / 0.25
    "an 80% reduction" / "cut by 80%" / "loses 80%" -> 0.2   (reduction BY x means 1 - x remains)
    "cut by three quarters" -> 0.25
    "about half" -> 0.5
- minimum_battery_reserve: keep at least some energy stored in the battery for some hours.
  value_kind = "reserve_kwh" with value in kWh, OR "reserve_percent_of_capacity" with value in percent (0..100)
  when the note says a percentage of the battery / capacity / state of charge. Do NOT convert percent to kWh yourself.
- no_charge_window: energy must not go INTO the battery for some hours: "do not charge", "charger isolated",
  "charging circuit down", "no top-up", "don't fill the battery", "battery intake disabled". value_kind = "none", value = 0.
- no_discharge_window: energy must not come OUT of the battery for some hours: "do not discharge", "no battery output",
  "do not draw / pull / take / supply from the battery", "battery must not feed the load", protection or relay tests.
  value_kind = "none", value = 0.
  Direction test: charging = energy INTO the battery; discharging = energy OUT OF the battery to the campus.
- max_grid_window: grid import / intake / draw / feeder / transformer / substation limit for some hours.
  value_kind = "max_grid_kwh", value = the cap per hour in kWh.
    If given in kW for one hour (e.g. "140 kW", "150 kW") or unit is omitted (e.g. "no more than 150", "cap intake at 160"),
    value is that number.
- no_op: the note does not change TODAY's demand, solar, battery or grid rules. This includes campus notices
  (menus, deadlines, bookings, library hours, sports), and ALSO ANY energy-related notes about another day
  ("tomorrow", "tomorrow morning", "tomorrow night", "next week", "next Tuesday", "yesterday", "last month").
  Energy directives for tomorrow or other days MUST be classified as no_op since today's schedule is unaffected.
  value_kind = "none", value = 0, windows = [].

TIME WINDOWS: whole hours, 24-hour clock. start_hour is INCLUDED, end_hour_exclusive is EXCLUDED.
  midnight = 0, noon = 12, 1 PM = 13, 11 PM = 23; "until midnight" or "to the end of the day" -> end_hour_exclusive = 24.
  "from 1 PM to 3 PM" -> {start_hour: 13, end_hour_exclusive: 15}
  "between 13:00 and 15:00" -> {13, 15}       "6 PM until 9 PM" -> {18, 21}       "10 AM until noon" -> {10, 12}
  "from one until three in the afternoon" -> {13, 15}       "all day" -> {0, 24}
  "10 PM to 2 AM" (crosses midnight) -> {start_hour: 22, end_hour_exclusive: 2}
  "dusk" or "sunset" -> 18:00 (hour 18). E.g. "from dusk until 9 PM" -> {start_hour: 18, end_hour_exclusive: 21}
  "dawn" or "sunrise" -> 06:00 (hour 6). E.g. "from dawn until 10 AM" -> {start_hour: 6, end_hour_exclusive: 10}
  Partial/colloquial hours: expand to cover the whole affected 1-hour slots.
    "quarter to 2 PM until 4 PM" (1:45 PM - 4:00 PM) touches hour 13, so {start_hour: 13, end_hour_exclusive: 16}
    "quarter past 5 PM until 8 PM" touches hour 17, so {start_hour: 17, end_hour_exclusive: 20}
  A note with two separate periods gets two windows. Notes with no time reference that clearly apply all day -> {0, 24}.

RULES: one directive per note; never invent a type outside the list; if a note is ambiguous between an energy
rule and a distractor, prefer the energy rule only when it clearly refers to today. explanation: one short
sentence (max 20 words) in plain language. Return only the JSON object."""

# Provider / model configuration (env). Groq is an OpenAI-compatible endpoint.
DEFAULT_GROQ_MODELS = "openai/gpt-oss-120b,openai/gpt-oss-20b,llama-3.3-70b-versatile"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _total_budget_s() -> float:
    # Judge timeout is 30 s; leave room for the LP, validation and network on top of the model call.
    return float(os.getenv("LLM_TIMEOUT_S", "20"))


def _attempt_timeout_s() -> float:
    return float(os.getenv("LLM_ATTEMPT_TIMEOUT_S", "12"))


def _providers() -> list[tuple[str, str, str, str]]:
    """Ordered (name, url, key, model) attempts, honouring LLM_PROVIDER as the preferred first."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    groq = [("groq", GROQ_URL, groq_key, m.strip()) for m in os.getenv("GROQ_MODELS", DEFAULT_GROQ_MODELS).split(",") if m.strip()] if groq_key else []
    openai = [("openai", OPENAI_URL, openai_key, os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL))] if openai_key else []
    preferred = os.getenv("LLM_PROVIDER", "groq").lower()
    return openai + groq if preferred == "openai" else groq + openai


def _payload(model: str, user_prompt: str, schema_mode: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        "temperature": 0,
        "max_completion_tokens": 1200,
        "response_format": (
            {"type": "json_schema", "json_schema": {"name": "interpretations", "schema": OUTPUT_SCHEMA, "strict": True}}
            if schema_mode
            else {"type": "json_object"}
        ),
    }
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "low"  # reasoning tokens count against the output budget
    return payload


async def _attempt(client: httpx.AsyncClient, name: str, url: str, key: str, model: str, user_prompt: str, timeout: float) -> dict[str, Any] | None:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for schema_mode in (True, False):
        try:
            resp = await client.post(url, headers=headers, json=_payload(model, user_prompt, schema_mode), timeout=timeout)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning("llm %s/%s: %s", name, model, type(e).__name__)
            return None
        if resp.status_code == 200:
            try:
                content = resp.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                return data if isinstance(data, dict) else None
            except (KeyError, IndexError, TypeError, ValueError):
                logger.warning("llm %s/%s: unparseable response", name, model)
                return None
        if resp.status_code == 400 and schema_mode:
            # Model doesn't support json_schema; retry once with json_object.
            logger.info("llm %s/%s: json_schema unsupported, using json_object", name, model)
            continue
        logger.warning("llm %s/%s: HTTP %d", name, model, resp.status_code)
        return None
    return None


def build_user_prompt(notes: list[str], battery: Battery) -> str:
    lines = [f"Battery capacity: {battery.capacity_kwh} kWh", f"Number of notes: {len(notes)}", "Operator notes:"]
    lines += [f"[{i}] {note}" for i, note in enumerate(notes)]
    return "\n".join(lines)


def _hedge_after_s() -> float:
    # If the first attempt has not answered by then, start a second one in parallel and take the
    # first valid answer. Provider tail latency (occasional 8-12 s answers) is what this cures.
    return float(os.getenv("LLM_HEDGE_AFTER_S", "2.5"))


async def _hedged(client: httpx.AsyncClient, attempts: list[tuple[str, str, str, str]], user_prompt: str, deadline: float) -> dict[str, Any] | None:
    """Run attempts with hedging: a new attempt starts when the previous one is silent for hedge_after s."""
    hedge_after = _hedge_after_s()
    pending: dict[asyncio.Task, tuple[str, str, float]] = {}
    next_i = 0
    last_launch = 0.0
    try:
        while True:
            now = time.monotonic()
            remaining = deadline - now
            can_launch = next_i < len(attempts) and remaining >= 2.0
            if can_launch and (not pending or now - last_launch >= hedge_after):
                name, url, key, model = attempts[next_i]
                next_i += 1
                last_launch = now
                task = asyncio.create_task(_attempt(client, name, url, key, model, user_prompt, min(_attempt_timeout_s(), remaining)))
                pending[task] = (name, model, now)
            if not pending:
                return None
            wait_for = remaining
            if next_i < len(attempts):
                wait_for = min(wait_for, max(0.05, hedge_after - (time.monotonic() - last_launch)))
            done, _ = await asyncio.wait(set(pending), timeout=max(0.0, wait_for), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                name, model, started = pending.pop(task)
                data = task.result() if not task.cancelled() and task.exception() is None else None
                if isinstance(data, dict) and isinstance(data.get("interpretations"), list):
                    logger.info("llm %s/%s ok in %.0f ms (attempt %d)", name, model, (time.monotonic() - started) * 1000, next_i)
                    return data
                logger.warning("llm %s/%s: no usable answer", name, model)
            if time.monotonic() >= deadline:
                logger.warning("llm: overall deadline reached")
                return None
    finally:
        for task in pending:
            task.cancel()


async def call_llm_interpreter(notes: list[str], battery: Battery) -> list[dict[str, Any]]:
    """Interpret every note concurrently (one request per note, hedged) under one overall deadline.

    Notes are independent by specification, so per-note requests keep each answer short (fast) and
    isolate a slow or failed answer to that note. Returns raw interpretation dicts keyed by
    note_index; missing notes are left out and the guardrail marks them unavailable.
    """
    attempts = _providers()
    if not attempts:
        logger.error("llm: no provider configured (set GROQ_API_KEY or OPENAI_API_KEY)")
        return []
    if len(attempts) == 1:
        attempts = attempts * 2  # single provider: hedge with a second call to the same model
    deadline = time.monotonic() + _total_budget_s()

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_hedged(client, attempts, build_user_prompt([note], battery), deadline) for note in notes],
            return_exceptions=True,
        )

    items: list[dict[str, Any]] = []
    for i, data in enumerate(results):
        if isinstance(data, dict):
            entries = [e for e in data["interpretations"] if isinstance(e, dict)]
            if entries:
                entry = dict(entries[0])
                entry["note_index"] = i  # each request saw a single note indexed 0
                items.append(entry)
                continue
        logger.warning("llm: note %d has no usable interpretation", i)
    if not items:
        logger.warning("llm: no usable interpretation; guardrail will degrade to no_op")
    return items
