import sys
import os
import json
import time

from ollama_client import call_ollama, extract_json, OllamaError
from models import NotesResponse

TRANSCRIPT_PATH = "transcript.txt"
OUTPUT_PATH = "notes.json"


def build_prompt(transcript: str) -> str:
    return f"""
You are an expert educational AI assistant.

Your ONLY task is to divide the lecture transcript into logical topics and
generate one structured study card per topic.

IMPORTANT RULES

- Use ONLY information present in the transcript.
- Do NOT use outside knowledge.
- Do NOT invent examples.
- Do NOT guess missing information.
- Return ONLY valid JSON.
- No markdown.
- No explanations outside JSON.
- If the transcript contains quotation marks ("), escape them as \\" inside JSON strings.
- Any code snippets must be returned as plain text with escaped quotes.
- Every object inside "content" must have EXACTLY two keys: "heading" and "text". Never add a third key. Never write an explanation or reasoning as a JSON key — all reasoning belongs inside the "text" value only.

Return ONLY this JSON format:

{{
    "notes": [
        {{
            "title": "",
            "content": [
                {{
                    "heading": "",
                    "text": ""
                }}
            ]
        }}
    ]
}}

====================================================
NOTES
====================================================

Divide the lecture into logical topics and generate one structured study card per topic.

Each note card has:

- "title": the name of the topic (e.g. "Variables", "While Loop", "Collections Framework").
- "content": a list of sections, each with a "heading" and "text".

Choose headings ONLY from this list, and ONLY when the transcript actually supports that heading:

- Definition
- Syntax
- Working
- Types
- Features
- Key Points
- Example
- Applications
- Advantages
- Disadvantages
- Important Notes

Requirements:

- Do NOT give every topic the same set of headings — include only the headings that fit what the transcript actually covers for that topic.
- Do NOT invent an "Example" section if the transcript has no example for that topic.
- Do NOT invent an "Advantages" or "Disadvantages" section unless the transcript actually discusses them.
- If a heading has nothing to say, do NOT include that heading at all — never write filler like "None provided" or "not mentioned". Omitting the heading is always correct; writing a placeholder is never correct.
- Follow the order the topics appear in the lecture.
- Avoid repeating the same topic twice.
- Use only information from the transcript — no outside knowledge, no guessing.
- Generate as many topic cards as the lecture naturally divides into.

Transcript:

{transcript}
"""


def main():
    started = time.time()
    print("[notes.py] START", file=sys.stderr)

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
    TEMPERATURES = [0.0, 0.4, 0.7]
    validated = None
    last_error = None
    last_raw_output = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw_output = call_ollama(prompt, temperature=TEMPERATURES[attempt - 1], num_predict=2600)
        except OllamaError as e:
            print(f"Failed to connect to Ollama: {e}", file=sys.stderr)
            sys.exit(1)

        last_raw_output = raw_output

        try:
            data = extract_json(raw_output)

            if "notes" not in data:
                wrong_keys = list(data.keys())
                raise ValueError(
                    f"Model returned the wrong JSON shape entirely (keys: {wrong_keys}) "
                    f"instead of a 'notes' field."
                )

            validated = NotesResponse(**data)
            break
        except Exception as e:
            last_error = e
            print(f"Notes Validation Failed (attempt {attempt}/{MAX_ATTEMPTS})!", file=sys.stderr)
            print(e, file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                print("Retrying generation...", file=sys.stderr)

    if validated is None:
        print("Notes Validation Failed after all retries!", file=sys.stderr)
        print(last_error, file=sys.stderr)
        print(last_raw_output, file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(validated.model_dump(), f, indent=4, ensure_ascii=False)

    finished = time.time()
    print(
        f"[notes.py] END (took {finished - started:.1f}s) "
        f"Output: {OUTPUT_PATH} Model: qwen2.5:3b Topics: {len(validated.notes)}",
        file=sys.stderr
    )
    print("notes.json generated successfully.")


if __name__ == "__main__":
    main()