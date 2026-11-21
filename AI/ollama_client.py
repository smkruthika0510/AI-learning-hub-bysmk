"""
Shared Ollama client for the AI Learning Hub pipeline.

Every AI script (summary.py, notes.py, quiz.py) calls call_ollama() from
here instead of calling requests.post() directly. This is the ONLY file
that should contain Ollama HTTP calls, retry logic, and model config.
"""

import sys
import time
import json
import requests

# -----------------------------
# Model configuration
# -----------------------------
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b"

DEFAULT_TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

# Ollama defaults to a small context window (often 2048-4096 tokens) unless
# told otherwise. A 25-30+ minute lecture transcript alone can be 5,000-6,000+
# tokens, which overflows a small window and pushes the JSON schema
# instructions at the start of the prompt out of the model's view — this is
# what causes long videos to drift into the wrong output shape or truncate
# while short videos work fine. qwen2.5:3b supports up to 32K context, so
# 16384 leaves real headroom for transcript + prompt + generation together.
DEFAULT_NUM_CTX = 16384


class OllamaError(Exception):
    """Raised when Ollama cannot be reached or returns an unusable response."""
    pass


def call_ollama(prompt, temperature=0.0, top_p=0.9, num_predict=1400, num_ctx=DEFAULT_NUM_CTX, timeout=DEFAULT_TIMEOUT_SECONDS):
    """
    Sends a prompt to Ollama and returns the raw text response (the
    "response" field of Ollama's /api/generate reply).

    Retries automatically on transient connection errors (e.g. Ollama
    momentarily unloading the model after an idle keep_alive window).
    Non-connection errors (bad status code, etc.) are not retried.

    Raises OllamaError if Ollama could not be reached after all attempts.
    """
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"[ollama_client] Calling Ollama model={OLLAMA_MODEL} num_ctx={num_ctx} (attempt {attempt}/{MAX_ATTEMPTS})...", file=sys.stderr)

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": temperature,
                        "top_p": top_p,
                        "num_predict": num_predict,
                        "num_ctx": num_ctx
                    }
                },
                timeout=timeout
            )

            response.raise_for_status()
            print("[ollama_client] Ollama responded successfully.", file=sys.stderr)
            return response.json()["response"]

        except requests.exceptions.ConnectionError as e:
            # Most "Failed to connect to Ollama" errors are a transient dropped
            # or stale connection. A short retry usually clears them without
            # needing a longer timeout or any architecture change.
            last_error = e
            print(f"[ollama_client] Connection attempt {attempt} failed: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                print(f"[ollama_client] Retrying in {RETRY_DELAY_SECONDS}s...", file=sys.stderr)
                time.sleep(RETRY_DELAY_SECONDS)

        except Exception as e:
            # Non-connection errors (bad status, timeout, etc.) are not retried.
            last_error = e
            break

    raise OllamaError(f"Failed to get a response from Ollama after {MAX_ATTEMPTS} attempts: {last_error}")


def extract_json(raw_text):
    """
    Parses raw_text (Ollama's response field) as JSON.

    Ollama is called with format="json" so this is normally a plain
    json.loads(), but this also strips accidental markdown code fences
    as a safety net in case the model wraps its output in ```json ... ```.
    """
    text = raw_text.strip()

    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)