"""LLM integration module.

Sends the user's request to Gemini with the prompt template from
prompts/agent_prompt.txt and returns the model's plan as a Python dict.
Handles the common API errors (429 = rate limit, 503 = model busy) by
retrying, then trying a backup model once.
"""
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

MAIN_MODEL = "gemini-3.8-flash"
BACKUP_MODEL = "gemini-3.5-flash"

with open(os.path.join(os.path.dirname(__file__), "prompts", "agent_prompt.txt")) as f:
    PROMPT_TEMPLATE = f.read()


def api_key_available():
    return bool(os.getenv("GEMINI_API_KEY"))


def ask_gemini(client, model, prompt):
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)


def get_plan(request_text, state_text):
    """Return (plan, error_message). One of the two is always None."""
    if not api_key_available():
        return None, "No GEMINI_API_KEY set"

    try:
        # A 20s per-call timeout keeps one slow Gemini call from hanging the
        # request; get_plan then falls back instead of being killed by the
        # web server's worker timeout.
        client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            http_options=types.HttpOptions(timeout=20000),
        )
    except Exception as e:
        return None, f"Could not start the Gemini client: {e}"
    prompt = PROMPT_TEMPLATE.replace("{state}", state_text).replace("{request}", request_text)

    # Try the main model 3 times, then the backup model once
    for model in [MAIN_MODEL] * 3 + [BACKUP_MODEL]:
        try:
            return ask_gemini(client, model, prompt), None
        except errors.APIError as e:
            # 503 = model busy, 429 = out of quota / rate limited
            if e.code not in (429, 503):
                return None, f"Gemini error: {e.code}"
            print(f"{model} failed ({e.code}), retrying...")
        except (json.JSONDecodeError, ValueError):
            return None, "The model did not return valid JSON"
        except Exception as e:
            return None, f"Could not reach Gemini: {e}"
    return None, "Gemini is busy or rate limited right now"
