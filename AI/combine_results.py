import sys
import os
import json
import time

from models import FinalResponse

SUMMARY_PATH = "summary.json"
NOTES_PATH = "notes.json"
QUIZ_PATH = "quiz.json"
OUTPUT_PATH = "final_output.json"


def load_json(path, stage_name):
    if not os.path.exists(path):
        print(f"{stage_name} output not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"{stage_name} output is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    started = time.time()
    print("[combine_results.py] START", file=sys.stderr)

    summary_data = load_json(SUMMARY_PATH, "Summary")
    notes_data = load_json(NOTES_PATH, "Notes")
    quiz_data = load_json(QUIZ_PATH, "Quiz")

    if "summary" not in summary_data:
        print(f"Summary output is missing the 'summary' field: {SUMMARY_PATH}", file=sys.stderr)
        sys.exit(1)

    if "notes" not in notes_data:
        print(f"Notes output is missing the 'notes' field: {NOTES_PATH}", file=sys.stderr)
        sys.exit(1)

    if "quiz" not in quiz_data:
        print(f"Quiz output is missing the 'quiz' field: {QUIZ_PATH}", file=sys.stderr)
        sys.exit(1)

    try:
        final = FinalResponse(
            summary=summary_data["summary"],
            notes=notes_data["notes"],
            quiz=quiz_data["quiz"]
        )
    except Exception as e:
        print("Failed to combine AI results!", file=sys.stderr)
        print(e, file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final.model_dump(), f, indent=4, ensure_ascii=False)

    finished = time.time()
    print(
        f"[combine_results.py] END (took {finished - started:.1f}s) "
        f"Output: {OUTPUT_PATH} Notes: {len(final.notes)} Quiz: {len(final.quiz)}",
        file=sys.stderr
    )
    print("final_output.json generated successfully.")


if __name__ == "__main__":
    main()