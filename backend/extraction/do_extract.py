"""DigitalOcean Gradient extraction (OpenAI-compatible) — primary LLM provider.

Mirrors `llm_extract.extract()`: full page-tagged text + section-7.4 photos in,
validated `BridgeExtraction` + usage out. Built on the OpenAI Chat Completions
shape (interleaved text + image_url parts), so any vision-capable DO model works.
Reuses the SAME system prompt and domain gate as the Gemini path — only the
transport changes.

`_chat()` is the shared low-level call (also used by enrichment.do_summary).
Model defaults to config.LLM_MODEL (validated: `llama-4-maverick`).
"""
import base64
import json

import requests

from backend import config
from backend.extraction.llm_extract import (
    _SYSTEM_PROMPT, _domain_gate, _mime, check_count, count_instruction,
)
from backend.extraction.schemas import BridgeExtraction
from backend.ingestion.pdf_photos import ExtractedImage


def data_uri(img: ExtractedImage) -> str:
    """An OpenAI-style base64 data URI for one extracted image."""
    return f"data:{_mime(img.ext)};base64,{base64.b64encode(img.image_bytes).decode()}"


def parse_json(content: str) -> dict:
    """Pull the JSON object out of a model reply (tolerates ``` fences / prose)."""
    s = content.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1:
        raise ValueError(f"no JSON object in model reply: {content[:200]!r}")
    return json.loads(s[i:j + 1])


def _chat(messages: list[dict], model: str, *, max_tokens: int, json_mode: bool = True,
          temperature: float = 0.0) -> tuple[str, dict]:
    """POST to the DO chat endpoint; return (content, usage). Retries without
    response_format if the model rejects JSON mode. temperature defaults to 0
    for deterministic, tighter, better-formed JSON (matches the Gemini path)."""
    payload: dict = {
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = requests.post(
        f"{config.DO_INFERENCE_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.DO_MODEL_ACCESS_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=config.DO_TIMEOUT_S,
    )
    if resp.status_code == 400 and json_mode:  # some models reject response_format
        return _chat(messages, model, max_tokens=max_tokens, json_mode=False)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} from {model}: {resp.text[:600]}")

    body = resp.json()
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError(
            f"{model} hit the output cap (max_tokens={max_tokens}) and truncated "
            f"its JSON mid-object — raise max_tokens for this call"
        )
    return choice["message"]["content"], body.get("usage", {})


def extract(text: str, *, model: str | None = None, expected_schaeden: int | None = None,
            feedback: str | None = None, temperature: float = 0.0) -> tuple[BridgeExtraction, dict]:
    """Run text-only extraction on a DO model. Returns (BridgeExtraction, usage).

    No images are sent: photo↔damage matching is resolved deterministically
    afterwards (ingestion.photo_match) from each damage's verbatim bild_ref.
    Dropping the inline images also cuts input tokens substantially.

    `expected_schaeden` (when known, born-digital only) pins the exact number of
    damages in the prompt and flags any mismatch — see llm_extract.count_instruction.
    `feedback` is the optional retry instruction (missing marker numbers); a small
    `temperature` bump on that retry helps the model find the dropped damages."""
    model = model or config.LLM_MODEL
    schema = json.dumps(BridgeExtraction.model_json_schema(), ensure_ascii=False)
    system = (
        _SYSTEM_PROMPT
        + "\n\nAntworte AUSSCHLIESSLICH mit EINEM JSON-Objekt nach diesem JSON-Schema "
        "(keine Erklärungen, kein Markdown):\n" + schema
    )

    user_content: list[dict] = [
        {"type": "text", "text": f"DOKUMENT:\n{text}"},
        {"type": "text", "text": "\n\nGib die Antwort als gültiges JSON gemäß dem Schema aus."},
    ]
    instr = count_instruction(expected_schaeden)
    if instr:
        user_content.append({"type": "text", "text": instr})
    if feedback:
        user_content.append({"type": "text", "text": feedback})

    content, u = _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        model, max_tokens=16000, temperature=temperature,
    )
    bridge = BridgeExtraction.model_validate(parse_json(content))
    _domain_gate(bridge)
    check_count(bridge, expected_schaeden, model)

    usage = {
        "input_tokens": u.get("prompt_tokens"),
        "output_tokens": u.get("completion_tokens"),
        "model": model,
    }
    return bridge, usage
