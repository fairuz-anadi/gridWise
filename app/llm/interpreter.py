"""LLM Interpreter client for operator notes.

Supports Groq LPU and OpenAI models with automatic failover, retries,
and robust JSON parsing.
"""
import json
import logging
import os
import re
from typing import Any

import httpx

from app.schemas import Battery

logger = logging.getLogger("gridwise.llm")

SYSTEM_PROMPT = """You are the GridWise operator note interpreter for a smart campus energy management system.
You will receive 1 to 3 operator notes, each indexed 0..N-1, along with the battery capacity in kWh.
You must interpret every operator note into a machine-checkable directive for today's 24-hour schedule.

Supported directive types and required structured_adjustment shapes:
1. "solar_reduction": {"hours": [...], "factor": number}
   - factor is the USABLE fraction remaining (between 0.0 and 1.0).
   - "80% reduction" means factor = 0.2 (1.0 - 0.80).
   - "drop to about 20%" or "one-fifth" means factor = 0.2.
   - "drop by 30%" means factor = 0.7.
   - "half of the forecast solar" means factor = 0.5.
   - "roughly 25% of the forecast" means factor = 0.25.
2. "minimum_battery_reserve": {"hours": [...], "minimum_energy_kwh": number}
   - If stated as a percentage of battery capacity (e.g., "50% of the battery capacity"), multiply that percentage by battery capacity_kwh.
   - Must be non-negative and <= battery capacity_kwh.
3. "no_charge_window": {"hours": [...]}
   - Charging disabled, isolated, or unavailable.
4. "no_discharge_window": {"hours": [...]}
   - Discharging disabled, unavailable, or prohibited.
5. "max_grid_window": {"hours": [...], "max_grid_kwh": number}
   - Grid import/intake/feeder cap in kWh.
6. "no_op": null
   - For any irrelevant note, distractor, or note not affecting today's 24-hour energy schedule (e.g. cafeteria menus, registration deadlines, room bookings, library hours, sports notices).
   - For "no_op", applies MUST be false and structured_adjustment MUST be null.

Time Window Conventions:
- Hours are whole-hour intervals from 0 through 23.
- The start hour is INCLUDED and the end hour is EXCLUDED.
- Hour mappings:
  * 12 AM (midnight) = 0
  * 1 AM = 1, 2 AM = 2, 3 AM = 3, 4 AM = 4, 5 AM = 5, 6 AM = 6
  * 7 AM = 7, 8 AM = 8, 9 AM = 9, 10 AM = 10, 11 AM = 11
  * 12 PM (noon) = 12
  * 1 PM = 13, 2 PM = 14, 3 PM = 15, 4 PM = 16, 5 PM = 17, 6 PM = 18
  * 7 PM = 19, 8 PM = 20, 9 PM = 21, 10 PM = 22, 11 PM = 23
- Examples:
  * "noon until 2 PM" -> [12, 13]
  * "2 AM until 5 AM" -> [2, 3, 4]
  * "1 PM to 3 PM" or "between 13:00 and 15:00" -> [13, 14]
  * "6 PM until 9 PM" -> [18, 19, 20]
  * "6 PM until 8 PM" -> [18, 19]
  * "10 AM until noon" -> [10, 11]
  * "2 PM until 4 PM" -> [14, 15]
  * "6 PM until 10 PM" -> [18, 19, 20, 21]
  * "7 PM until 9 PM" -> [19, 20]
  * "7 PM until 10 PM" -> [19, 20, 21]
  * "11 AM until 1 PM" -> [11, 12]
  * "5 PM until 7 PM" -> [17, 18]
  * "between 11 AM and 2 PM" -> [11, 12, 13]
- "hours" must contain unique integers in strictly ascending order.

applies Semantics:
- applies must be false ONLY for "no_op".
- applies must be true for all other 5 directive types.

Return JSON in this exact structure:
{
  "interpretations": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {"hours": [12, 13], "factor": 0.25},
      "explanation": "Brief explanation of the directive"
    }
  ]
}
"""


async def _call_groq(
    user_prompt: str,
    groq_api_key: str,
    models: list[str] = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
) -> dict[str, Any] | None:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for model in models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_completion_tokens": 400
            }
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
                elif resp.status_code == 429:
                    logger.warning("Groq model %s hit 429, trying next model", model)
                    continue
                else:
                    logger.warning("Groq error %d: %s", resp.status_code, resp.text[:100])
            except Exception as e:
                logger.error("Exception calling Groq with model %s: %s", model, e)
                continue
    return None


async def _call_openai(
    user_prompt: str,
    openai_api_key: str,
    models: list[str] = ["gpt-4.1-mini", "gpt-4o-mini"]
) -> dict[str, Any] | None:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for model in models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 500
            }
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
                elif resp.status_code == 429:
                    logger.warning("OpenAI model %s hit 429, trying next model", model)
                    continue
                else:
                    logger.warning("OpenAI model %s error %d: %s", model, resp.status_code, resp.text[:100])
            except Exception as e:
                logger.error("Exception calling OpenAI with model %s: %s", model, e)
                continue
    return None


def _extract_interpretations(result: Any) -> list[dict[str, Any]] | None:
    if result and isinstance(result, dict):
        if "interpretations" in result and isinstance(result["interpretations"], list):
            return result["interpretations"]
        elif "directives" in result and isinstance(result["directives"], list):
            return result["directives"]
    elif isinstance(result, list):
        return result
    return None


async def call_llm_interpreter(notes: list[str], battery: Battery) -> list[dict[str, Any]]:
    """Invoke LLM with multi-provider failover to interpret operator notes.
    
    Primary provider is OpenAI with automatic fallback to Groq.
    Returns a list of raw dicts or fallback safe defaults.
    """
    user_content = f"Battery capacity: {battery.capacity_kwh} kWh\nOperator notes:\n"
    for i, note in enumerate(notes):
        user_content += f"[{i}] {note}\n"

    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if provider == "openai":
        if openai_key:
            parsed_result = await _call_openai(user_content, openai_key)
            extracted = _extract_interpretations(parsed_result)
            if extracted is not None:
                return extracted
            logger.warning("OpenAI did not return valid interpretations; attempting fallback to Groq")

        if groq_key:
            logger.info("Failing over from OpenAI to Groq")
            parsed_result = await _call_groq(user_content, groq_key)
            extracted = _extract_interpretations(parsed_result)
            if extracted is not None:
                return extracted
    else:
        if groq_key:
            parsed_result = await _call_groq(user_content, groq_key)
            extracted = _extract_interpretations(parsed_result)
            if extracted is not None:
                return extracted
            logger.warning("Groq did not return valid interpretations; attempting fallback to OpenAI")

        if openai_key:
            logger.info("Failing over from Groq to OpenAI")
            parsed_result = await _call_openai(user_content, openai_key)
            extracted = _extract_interpretations(parsed_result)
            if extracted is not None:
                return extracted

    # Controlled safe failure: return empty list so guardrail can safely fallback to no_op
    logger.warning("LLM returned malformed or empty output; invoking guardrail fallback")
    return []
