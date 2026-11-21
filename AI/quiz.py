import sys
import os
import json
import time

from ollama_client import call_ollama, extract_json, OllamaError
from models import QuizResponse


TRANSCRIPT_PATH = "transcript.txt"
OUTPUT_PATH = "quiz.json"


def build_prompt(transcript: str) -> str:

    # Estimate lecture length from transcript size.
    word_count = len(transcript.split())

    if word_count <= 1500:
        question_count = 5
    elif word_count <= 4500:
        question_count = 10
    else:
        question_count = 15

    return f"""
You are an expert educational quiz generator.

Your ONLY task is to create a multiple-choice quiz from the
lecture transcript provided below.

IMPORTANT RULES:

- Use ONLY information explicitly present in the transcript.
- Do NOT use outside knowledge.
- Do NOT invent facts.
- Do NOT invent examples.
- Do NOT explain answers.
- Do NOT add explanations to questions.
- Do NOT add explanations to options.
- Do NOT repeat questions.
- Follow the order of concepts in the transcript.
- Return ONLY valid JSON.
- Do NOT return markdown.
- Do NOT return ```json.
- Do NOT write anything before or after the JSON.

NUMBER OF QUESTIONS:

Generate EXACTLY {question_count} questions.

QUESTION RULES:

- Every question must be based directly on the transcript.
- Each question must be short and clear.
- Keep every question below 25 words.
- Each question must have exactly 4 options.
- Each option must be short.
- Keep every option below 15 words.
- Only ONE option can be correct.
- The correct answer must exactly match one of the four options.
- Do NOT explain why the answer is correct.
- Do NOT repeat the question inside an option.
- Do NOT write paragraphs inside options.
- Do NOT include notes or explanations in the quiz.
- Do NOT use newline characters inside strings.
- Do NOT use quotation marks inside strings unless properly escaped.

VERY IMPORTANT:

BAD OPTION:

"Java arrays use contiguous memory and therefore provide fast access.
This means that arrays are efficient because the JVM stores elements
together. This is useful for many reasons..."

GOOD OPTION:

"Arrays use contiguous memory"

Every option must look like the GOOD OPTION:
short, direct, and concise.

Return EXACTLY this structure:

{{
    "quiz": [
        {{
            "question": "Question?",
            "options": [
                "Option A",
                "Option B",
                "Option C",
                "Option D"
            ],
            "answer": "Option A"
        }}
    ]
}}

Before returning the JSON, internally check:

1. There are exactly {question_count} questions.
2. Every question has exactly 4 options.
3. Every answer exactly matches one option.
4. There are no duplicate questions.
5. No option contains an explanation.
6. No option is a long paragraph.
7. The output is valid JSON.
8. There is nothing outside the JSON.

LECTURE TRANSCRIPT:

{transcript}
"""


def validate_quiz(candidate: QuizResponse) -> None:
    """Extra checks on top of the Pydantic model. Raises ValueError on problems."""

    if not candidate.quiz:
        raise ValueError("Quiz contains no questions.")

    seen_questions = set()

    for index, q in enumerate(candidate.quiz, start=1):

        question_text = q.question.strip()

        if not question_text:
            raise ValueError(f"Question {index} is empty.")

        normalized = question_text.lower()
        if normalized in seen_questions:
            raise ValueError(f"Duplicate question found: {question_text}")
        seen_questions.add(normalized)

        if len(q.options) != 4:
            raise ValueError(f"Question {index} does not have exactly 4 options.")

        cleaned_options = []
        for option in q.options:
            option = str(option).strip()
            if not option:
                raise ValueError(f"Question {index} contains an empty option.")
            cleaned_options.append(option)
        q.options = cleaned_options

        if len(set(o.lower() for o in q.options)) != 4:
            raise ValueError(f"Question {index} contains duplicate options.")

        q.answer = q.answer.strip()

        if not q.answer:
            raise ValueError(f"Question {index} has an empty answer.")

        if q.answer not in q.options:
            raise ValueError(
                f"Answer '{q.answer}' does not match any option "
                f"for question '{q.question}'."
            )


def main():

    started = time.time()

    print("[quiz.py] START", file=sys.stderr)

    # ============================================================
    # READ TRANSCRIPT
    # ============================================================

    if not os.path.exists(TRANSCRIPT_PATH):
        print("Transcript file not found!", file=sys.stderr)
        sys.exit(1)

    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        transcript = f.read().strip()

    if not transcript:
        print("Transcript is empty!", file=sys.stderr)
        sys.exit(1)

    print(
        f"[quiz.py] Transcript length: {len(transcript)} characters",
        file=sys.stderr
    )

    # ============================================================
    # BUILD PROMPT
    # ============================================================

    prompt = build_prompt(transcript)

    # ============================================================
    # GENERATE QUIZ
    # ============================================================

    MAX_ATTEMPTS = 3

    # temperature 0.0 is deterministic: retrying with the same input would
    # just reproduce the same bad output, so each retry is a bit more random.
    TEMPERATURES = [0.0, 0.3, 0.6]

    validated = None
    last_error = None
    last_raw_output = None

    for attempt in range(1, MAX_ATTEMPTS + 1):

        print(
            f"[quiz.py] Generation attempt {attempt}/{MAX_ATTEMPTS}",
            file=sys.stderr
        )

        # --------------------------------------------------------
        # CALL OLLAMA
        # --------------------------------------------------------

        try:
            raw_output = call_ollama(
                prompt,
                temperature=TEMPERATURES[attempt - 1],
                num_predict=4000
            )

        except OllamaError as e:
            print(f"Failed to connect to Ollama: {e}", file=sys.stderr)
            sys.exit(1)

        last_raw_output = raw_output

        print(
            f"[quiz.py] Ollama response length: {len(raw_output)} characters",
            file=sys.stderr
        )

        # --------------------------------------------------------
        # SAVE RAW OUTPUT FOR DEBUGGING
        # --------------------------------------------------------

        try:
            with open("quiz_raw_output.txt", "w", encoding="utf-8") as f:
                f.write(raw_output)
        except Exception:
            pass

        # --------------------------------------------------------
        # PARSE AND VALIDATE JSON
        # --------------------------------------------------------

        try:
            data = extract_json(raw_output)

            candidate = QuizResponse(**data)

            validate_quiz(candidate)

            validated = candidate

            print("[quiz.py] Quiz validation successful.", file=sys.stderr)

            break

        except Exception as e:

            last_error = e

            print(
                f"Quiz Validation Failed (attempt {attempt}/{MAX_ATTEMPTS})!",
                file=sys.stderr
            )

            print(str(e), file=sys.stderr)

            if attempt < MAX_ATTEMPTS:
                print("Retrying generation...", file=sys.stderr)
                time.sleep(2)

    # ============================================================
    # ALL ATTEMPTS FAILED
    # ============================================================

    if validated is None:

        print("Quiz Validation Failed after all retries!", file=sys.stderr)

        print(last_error, file=sys.stderr)

        if last_raw_output:
            print("===== RAW OLLAMA OUTPUT =====", file=sys.stderr)
            print(last_raw_output, file=sys.stderr)

        sys.exit(1)

    # ============================================================
    # SAVE QUIZ JSON
    # ============================================================

    try:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(
                validated.model_dump(),
                f,
                indent=4,
                ensure_ascii=False
            )

    except Exception as e:
        print(f"Failed to save quiz.json: {e}", file=sys.stderr)
        sys.exit(1)

    # ============================================================
    # FINISHED
    # ============================================================

    finished = time.time()

    print(
        f"[quiz.py] END (took {finished - started:.1f}s) "
        f"Output: {OUTPUT_PATH} "
        f"Model: qwen2.5:3b "
        f"Questions: {len(validated.quiz)}",
        file=sys.stderr
    )

    print("quiz.json generated successfully.")


if __name__ == "__main__":
    main()