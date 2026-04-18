"""
TruthLens — Backend verification logic.
Python port of geminiService.ts + openaiService.ts.
"""
import base64
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
load_dotenv(Path(__file__).parent.parent / ".env")

import google.generativeai as genai
from openai import OpenAI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MODEL_PREFERENCE = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-pro",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite-001",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

MAX_RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY_MS = 1000  # milliseconds

SYSTEM_INSTRUCTION = (
    "You are an expert fact-checker and digital forensics analyst.\n"
    "Your goal is high factual accuracy.\n\n"
    "Rules:\n"
    "1. Break input into core verifiable claims.\n"
    "2. Verify each claim preferring authoritative sources "
    "(official statements, major wire services, peer-reviewed/government data).\n"
    "3. Distinguish between false, misleading (partly true/out-of-context), and unverified.\n"
    "4. For image claims, include OCR/readability issues and visual manipulation indicators.\n"
    "5. Assign aiProbability (0-100) only from concrete indicators, not guesswork.\n"
    "6. Return ONE JSON object with keys: verdict, aiProbability, summary, detailedAnalysis, sources.\n"
    "   verdict must be one of: Real, Fake, Misleading, Unverified.\n"
    "   sources is an array of {title, url} objects."
)

OPENAI_SYSTEM_INSTRUCTION = (
    "You are an expert fact-checker. Focus on high factual accuracy.\n"
    'Return a JSON object with these exact keys:\n'
    '{\n'
    '  "verdict": "Real" or "Fake" or "Misleading" or "Unverified",\n'
    '  "aiProbability": number 0-100,\n'
    '  "summary": "Brief summary string",\n'
    '  "detailedAnalysis": ["point 1", "point 2"],\n'
    '  "sources": [{"title": "source title", "url": "https://..."}]\n'
    '}'
)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------
def build_service_unavailable_result(reason: str, context_text: str, has_image: bool) -> dict:
    if context_text.strip():
        context_hint = f"Input received ({min(len(context_text.strip()), 240)} chars of text)."
    elif has_image:
        context_hint = "Image input received."
    else:
        context_hint = "No input context attached."

    return {
        "verdict": "Unverified",
        "aiProbability": 0,
        "summary": f"Live verification is temporarily unavailable ({reason}). Returning a safe fallback result.",
        "detailedAnalysis": [
            "No authoritative claim assessment could be completed because the Gemini API request did not succeed.",
            context_hint,
            "Rotate/regenerate your Gemini API key in Google AI Studio, update .env, restart the server, then retry.",
        ],
        "sources": [],
    }


# ---------------------------------------------------------------------------
# Error classifiers
# ---------------------------------------------------------------------------
def _msg(error: Exception) -> str:
    return str(error).lower()


def is_model_name_error(error: Exception) -> bool:
    m = _msg(error)
    return "model" in m and any(k in m for k in ("not found", "unsupported", "not available", "unknown"))


def is_permission_denied_error(error: Exception) -> bool:
    m = _msg(error)
    return "permission_denied" in m or "denied access" in m or ("403" in m and "denied" in m)


def is_quota_error(error: Exception) -> bool:
    m = _msg(error)
    return "429" in m or "resource_exhausted" in m or "quota" in m


def is_service_unavailable_error(error: Exception) -> bool:
    m = _msg(error)
    return any(k in m for k in (
        "503", "unavailable", "high demand", "spikes in demand", "temporarily unavailable"
    ))


def is_authentication_error(error: Exception) -> bool:
    m = _msg(error)
    return "401" in m or "unauthorized" in m or "invalid api key" in m


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clamp_probability(value) -> int:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, round(n)))


def normalize_verdict(value) -> str:
    if value in ("Real", "Fake", "Misleading", "Unverified"):
        return value
    return "Unverified"


def normalize_sources(value) -> list:
    if not isinstance(value, list):
        return []
    seen = set()
    out = []
    for item in value:
        title = (item.get("title") or "").strip() if isinstance(item, dict) else ""
        url = (item.get("url") or "").strip() if isinstance(item, dict) else ""
        if not title or not url:
            continue
        if not re.match(r"^https?://", url, re.IGNORECASE):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append({"title": title, "url": url})
    return out


def normalize_result(raw: dict) -> dict:
    detailed = raw.get("detailedAnalysis", [])
    if isinstance(detailed, list):
        detailed = [x.strip() for x in detailed if isinstance(x, str) and x.strip()]
    else:
        detailed = []

    summary = raw.get("summary", "")
    if not isinstance(summary, str) or not summary.strip():
        summary = "No summary provided."

    return {
        "verdict": normalize_verdict(raw.get("verdict")),
        "aiProbability": clamp_probability(raw.get("aiProbability", 0)),
        "summary": summary.strip(),
        "detailedAnalysis": detailed,
        "sources": normalize_sources(raw.get("sources")),
    }


def parse_json_from_text(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = re.sub(r"```json\n?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```\n?", "", cleaned).strip()

    raw_obj = None
    try:
        raw_obj = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                raw_obj = json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None

    normalized = normalize_result(raw_obj)
    if not normalized["detailedAnalysis"] and normalized["summary"] == "No summary provided.":
        return None
    return normalized


def get_retry_delay(attempt: int) -> float:
    base = RETRY_BASE_DELAY_MS * (2 ** (attempt - 1)) / 1000.0
    jitter = random.randint(0, 250) / 1000.0
    return base + jitter


def normalize_model_name(model_name: str) -> str:
    if not model_name:
        return ""
    return model_name.removeprefix("models/").strip()


def list_supported_gemini_models() -> list:
    supported = []
    seen = set()

    for model in genai.list_models():
        model_name = normalize_model_name(getattr(model, "name", ""))
        methods = getattr(model, "supported_generation_methods", []) or []
        if not model_name or "generateContent" not in methods or model_name in seen:
            continue
        seen.add(model_name)
        supported.append(model_name)

    return supported


def build_gemini_model_order(model_from_env: Optional[str]) -> list:
    supported_models = list_supported_gemini_models()
    supported_set = set(supported_models)

    ordered = []
    preferred_candidates = []

    env_model = normalize_model_name(model_from_env or "")
    if env_model:
        preferred_candidates.append(env_model)

    preferred_candidates.extend(DEFAULT_MODEL_PREFERENCE)
    preferred_candidates.extend(supported_models)

    for candidate in preferred_candidates:
        normalized = normalize_model_name(candidate)
        if not normalized or normalized in ordered:
            continue
        if supported_set and normalized not in supported_set:
            continue
        ordered.append(normalized)

    if not ordered:
        ordered = supported_models[:]

    if env_model and env_model not in supported_set:
        print(f"[TruthLens] Ignoring unsupported GEMINI_MODEL={env_model}; using ListModels results instead.")

    if not ordered:
        raise RuntimeError(
            "Gemini returned no models that support generateContent. "
            "Check the API key, project access, and model availability."
        )

    print(f"[TruthLens] Gemini model order: {', '.join(ordered)}")
    return ordered


def supports_gemini_search_grounding() -> bool:
    return hasattr(genai.types, "GoogleSearch")


# ---------------------------------------------------------------------------
# Gemini client setup
# ---------------------------------------------------------------------------
def configure_gemini() -> str:
    """Configure genai and return the validated API key."""
    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip().strip("'\"")

    if not api_key:
        raise ValueError(
            "Missing GEMINI_API_KEY in environment. Set it in .env and restart the server."
        )
    if not api_key.startswith("AIza"):
        raise ValueError(
            "Invalid Gemini API key format. Keys from Google AI Studio start with 'AIza'. "
            f"Got: {api_key[:6]}..."
        )
    genai.configure(api_key=api_key)
    return api_key


# ---------------------------------------------------------------------------
# Gemini generation
# ---------------------------------------------------------------------------
def _call_gemini(model_name: str, contents, use_grounding: bool) -> genai.types.GenerateContentResponse:
    """
    Call Gemini once.
    IMPORTANT: response_mime_type='application/json' is incompatible with grounding tools.
    When grounding is on, we get free-text and parse JSON ourselves.
    When grounding is off, we ask for JSON mime type for reliability.
    """
    if use_grounding and supports_gemini_search_grounding():
        # Grounding mode: plain text response, we parse JSON from it
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
        )
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,
        )
    else:
        if use_grounding:
            print("[TruthLens] Gemini search grounding is unavailable in the installed SDK; using non-grounded requests.")
        # No grounding: request JSON directly
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        )

    return model.generate_content(contents, generation_config=generation_config)


def _generate_with_retry(model_name: str, contents, use_grounding: bool):
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            return _call_gemini(model_name, contents, use_grounding)
        except Exception as error:
            last_error = error
            if not is_service_unavailable_error(error) or attempt == MAX_RETRY_ATTEMPTS:
                raise
            time.sleep(get_retry_delay(attempt))
    raise last_error


def _build_contents(parts: list, with_grounding: bool) -> list:
    instruction = (
        "Fact-check this content using web search. "
        "Return ONLY a valid JSON object with keys: verdict, aiProbability, summary, detailedAnalysis, sources."
        if with_grounding
        else
        "Fact-check this content using your knowledge. "
        "Return ONLY a valid JSON object with keys: verdict, aiProbability, summary, detailedAnalysis, sources."
    )
    return parts + [{"text": instruction}]


def _run_analysis(model_name: str, parts: list, with_grounding: bool):
    contents = _build_contents(parts, with_grounding)
    return _generate_with_retry(model_name, contents, with_grounding)


def _run_json_repair(model_name: str, raw_text: str) -> Optional[dict]:
    repair_prompt = (
        f"Convert the following model output into a single valid JSON object. "
        f"Do not add markdown fences. Output ONLY the JSON.\n\nText to convert:\n{raw_text}"
    )
    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        response = model.generate_content(repair_prompt)
        if not response.text:
            return None
        return parse_json_from_text(response.text)
    except Exception as e:
        print(f"JSON repair failed: {e}")
        return None


# ---------------------------------------------------------------------------
# OpenAI fallback
# ---------------------------------------------------------------------------
def verify_with_openai(text: str, image_data: Optional[dict]) -> Optional[dict]:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip().strip("'\"")
    if not api_key:
        return None

    try:
        client = OpenAI(api_key=api_key)
        content = []
        if text.strip():
            content.append({"type": "text", "text": f"Verify this claim: {text}"})
        if image_data:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_data['mimeType']};base64,{image_data['data']}"
                },
            })

        if not content:
            return None

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": OPENAI_SYSTEM_INSTRUCTION},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
        )
        result_text = response.choices[0].message.content
        if not result_text:
            return None

        parsed = json.loads(result_text)
        return {
            "verdict": normalize_verdict(parsed.get("verdict", "Unverified")),
            "aiProbability": clamp_probability(parsed.get("aiProbability", 0)),
            "summary": parsed.get("summary", "No summary provided."),
            "detailedAnalysis": parsed.get("detailedAnalysis", []),
            "sources": normalize_sources(parsed.get("sources", [])),
        }
    except Exception as e:
        print(f"OpenAI verification failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def verify_content(text: str, image_data: Optional[dict]) -> dict:
    try:
        # Build parts
        parts = []
        if image_data:
            # Pass base64 string directly (don't decode to bytes)
            parts.append({
                "inline_data": {
                    "data": image_data["data"],
                    "mime_type": image_data["mimeType"],
                }
            })
        if text.strip():
            parts.append({"text": f'Content to verify:\n"""\n{text}\n"""'})

        if not parts:
            raise ValueError("Please provide either text or an image to verify.")

        configure_gemini()

        model_from_env = (os.environ.get("GEMINI_MODEL") or "").strip().strip("'\"") or None
        models_to_try = build_gemini_model_order(model_from_env)

        response = None
        used_model = ""
        last_model_error: Optional[Exception] = None
        used_grounding = True
        grounding_supported = supports_gemini_search_grounding()

        def run_across_models(with_grounding: bool) -> None:
            nonlocal response, used_model, last_model_error, used_grounding
            for model_name in models_to_try:
                try:
                    resp = _run_analysis(model_name, parts, with_grounding)
                    response = resp
                    used_model = model_name
                    used_grounding = with_grounding
                    print(f"[TruthLens] Used model={model_name}, grounding={with_grounding}")
                    return
                except Exception as error:
                    print(f"[TruthLens] Model {model_name} failed (grounding={with_grounding}): {error}")
                    last_model_error = error
                    if is_model_name_error(error) or is_quota_error(error) or is_service_unavailable_error(error):
                        continue
                    if with_grounding and (
                        is_permission_denied_error(error)
                        or "grounding" in str(error).lower()
                        or "invalid_argument" in str(error).lower()
                        or "invalid request" in str(error).lower()
                        or "google_search" in str(error).lower()
                    ):
                        continue
                    raise

        # Try with grounding first
        if grounding_supported:
            run_across_models(True)
        else:
            used_grounding = False
            print("[TruthLens] Skipping Gemini grounding because the installed SDK does not support it.")

        # If all grounding attempts failed, try without grounding.
        if response is None:
            if grounding_supported:
                print("[TruthLens] All grounding attempts failed, retrying without grounding...")
            run_across_models(False)

        # Final fallback: OpenAI
        if response is None:
            print("[TruthLens] All Gemini models failed, trying OpenAI fallback...")
            try:
                openai_result = verify_with_openai(text, image_data)
                if openai_result:
                    return openai_result
            except Exception as e:
                print(f"[TruthLens] OpenAI fallback also failed: {e}")

            if last_model_error:
                if is_quota_error(last_model_error):
                    return build_service_unavailable_result("quota/rate limit", text, bool(image_data))
                if is_service_unavailable_error(last_model_error):
                    return build_service_unavailable_result("service temporarily unavailable", text, bool(image_data))
                if is_permission_denied_error(last_model_error):
                    raise PermissionError(
                        "PERMISSION_DENIED (403): Your Gemini API key is blocked or restricted. "
                        "Create a new key at https://aistudio.google.com/apikey and update .env."
                    )

            raise RuntimeError(
                f"None of the configured Gemini models worked ({', '.join(models_to_try)}). "
                + (str(last_model_error) if last_model_error else "Unknown error.")
            )

        # Parse the response
        raw_text = ""
        try:
            raw_text = response.text or ""
        except Exception:
            pass

        parsed = parse_json_from_text(raw_text) if raw_text else None

        # Attempt JSON repair if parsing failed
        if not parsed and used_model and raw_text:
            print("[TruthLens] Primary parse failed, attempting JSON repair...")
            parsed = _run_json_repair(used_model, raw_text)

        if not parsed:
            raise RuntimeError(
                "Failed to parse the AI response into a valid result. Please retry."
            )

        # Extract grounding sources from metadata if the JSON didn't contain any
        if used_grounding and len(parsed.get("sources", [])) == 0:
            try:
                candidates = response.candidates or []
                if candidates:
                    gm = getattr(candidates[0], "grounding_metadata", None)
                    chunks = getattr(gm, "grounding_chunks", []) or []
                    extracted = []
                    seen = set()
                    for chunk in chunks:
                        web = getattr(chunk, "web", None)
                        url = getattr(web, "uri", None)
                        title = getattr(web, "title", None)
                        if not url or not title or url in seen:
                            continue
                        if not re.match(r"^https?://", url, re.IGNORECASE):
                            continue
                        seen.add(url)
                        extracted.append({"title": title, "url": url})
                    if extracted:
                        parsed["sources"] = extracted
            except Exception as e:
                print(f"[TruthLens] Could not extract grounding sources: {e}")

        return parsed

    except (ValueError, PermissionError, RuntimeError):
        raise
    except Exception as error:
        print(f"[TruthLens] Unexpected error: {error}")
        message = str(error)
        lower = message.lower()

        if "429" in message or "resource_exhausted" in lower or "quota" in lower:
            return build_service_unavailable_result("quota/rate limit", text, bool(image_data))
        if is_service_unavailable_error(error):
            return build_service_unavailable_result("service temporarily unavailable", text, bool(image_data))
        if is_authentication_error(error):
            raise ValueError(
                "Authentication failed: Invalid or missing Gemini API key. "
                "Set GEMINI_API_KEY in .env, then restart the server."
            )
        if "400" in message or "invalid_argument" in lower:
            raise ValueError("Invalid request sent to Gemini. Please check your input and retry.")
        if "403" in message or "permission_denied" in lower:
            raise PermissionError(
                "PERMISSION_DENIED (403): This API key is blocked. "
                "Create a new key at https://aistudio.google.com/apikey."
            )

        raise RuntimeError(message or "Failed to verify the content. Please try again.")
