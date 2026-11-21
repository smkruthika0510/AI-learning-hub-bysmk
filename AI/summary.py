import sys
import os
import json
import time

from ollama_client import call_ollama, extract_json, OllamaError
from models import Summary

TRANSCRIPT_PATH = "transcript.txt"
OUTPUT_PATH = "summary.json"


def build_prompt(transcript: str) -> str:
    return f"""
You are an expert educational AI assistant.

Your ONLY task is to convert the lecture transcript into a summary.

IMPORTANT RULES

- Use ONLY information present in the transcript.
- Do NOT use outside knowledge.
- Do NOT invent examples.
- Do NOT guess missing information.
- Return ONLY valid JSON.
- No markdown.
- No explanations outside JSON.
- If the transcript contains quotation marks ("), escape them as \\" inside JSON strings.

Return ONLY this JSON format — exactly one key, "summary", and nothing else:

{{
    "summary": ""
}}

Do NOT return any other keys such as "videoId", "title", "description", "topics", or "codeSnippets". Do NOT extract metadata about the video. Your only output is a single JSON object with one key: "summary".

Requirements for the summary:

- Write in paragraph form.
- Follow the lecture from beginning to end.
- Cover all important concepts.
- Use only information from the transcript.
- Do not repeat information.
- Do not use bullet points.

Length:

- Short lecture: 300-400 words
- Medium lecture: 400-550 words
- Long lecture: 550-700 words

Transcript:

{transcript}
"""


def main():
    started = time.time()
    print("[summary.py] START", file=sys.stderr)

    if not os.path.exists(TRANSCRIPT_PATH):
        print("Transcript file not found!", file=sys.stderr)
        sys.exit(1)

    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        transcript = f.read().strip()

    if not transcript:
        print("Transcript is empty!", file=sys.stderr)
        sys.exit(1)

    prompt = build_prompt(transcript)

    MAX_ATTEMPTS = 3
    # temperature=0.0 is deterministic — retrying with the same input at
    # temperature 0 just reproduces the exact same output, which does
    # nothing against a systematic mistake (e.g. the model latching onto
    # the wrong JSON schema). Increasing temperature on each retry gives
    # the model an actual chance to produce something different.
    TEMPERATURES = [0.0, 0.4, 0.7]
    validated = None
    last_error = None
    last_raw_output = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw_output = call_ollama(prompt, temperature=TEMPERATURES[attempt - 1], num_predict=2200)
        except OllamaError as e:
            print(f"Failed to connect to Ollama: {e}", file=sys.stderr)
            sys.exit(1)

        last_raw_output = raw_output

        try:
            data = extract_json(raw_output)

            if "summary" not in data:
                wrong_keys = list(data.keys())
                raise ValueError(
                    f"Model returned the wrong JSON shape entirely (keys: {wrong_keys}) "
                    f"instead of a 'summary' field — it likely pattern-matched onto a "
                    f"different task."
                )

            validated = Summary(**data)
            break
        except Exception as e:
            last_error = e
            print(f"Summary Validation Failed (attempt {attempt}/{MAX_ATTEMPTS})!", file=sys.stderr)
            print(e, file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                print("Retrying generation...", file=sys.stderr)

    if validated is None:
        print("Summary Validation Failed after all retries!", file=sys.stderr)
        print(last_error, file=sys.stderr)
        print(last_raw_output, file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(validated.model_dump(), f, indent=4, ensure_ascii=False)

    finished = time.time()
    print(
        f"[summary.py] END (took {finished - started:.1f}s) "
        f"Output: {OUTPUT_PATH} Model: qwen2.5:3b",
        file=sys.stderr
    )
    print("summary.json generated successfully.")


if __name__ == "__main__":
    main()