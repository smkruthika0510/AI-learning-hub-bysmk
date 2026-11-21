"""
Pydantic models for the AI Learning Hub pipeline.

Each AI script validates its own output against these models before
writing its JSON file, so a malformed model response fails fast at the
stage that produced it instead of surfacing as a confusing error later
in combine_results.py or in ASP.NET Core.

Requires pydantic >= 2 (uses field_validator). If this project is pinned
to pydantic 1.x, swap @field_validator(...) / @classmethod for @validator(...).
"""

from typing import List
from pydantic import BaseModel, field_validator


# -----------------------------
# Notes
# -----------------------------

class NoteSection(BaseModel):
    heading: str
    text: str


class Note(BaseModel):
    title: str
    content: List[NoteSection]

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Note title cannot be empty.")
        return v.strip()

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v):
        if len(v) < 1:
            raise ValueError("Note has no content sections.")
        return v


# -----------------------------
# summary.py output
# -----------------------------

class Summary(BaseModel):
    summary: str

    @field_validator("summary")
    @classmethod
    def summary_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Summary cannot be empty.")
        return v.strip()


# -----------------------------
# notes.py output
# -----------------------------

class NotesResponse(BaseModel):
    notes: List[Note]

    @field_validator("notes")
    @classmethod
    def at_least_one_note(cls, v):
        if len(v) < 1:
            raise ValueError("At least one note is required.")
        return v


# -----------------------------
# quiz.py output
# -----------------------------

class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    answer: str

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Question cannot be empty.")
        return v.strip()

    @field_validator("options")
    @classmethod
    def exactly_four_options(cls, v):
        if len(v) != 4:
            raise ValueError(f"Each question must have exactly 4 options, got {len(v)}.")
        return [opt.strip() for opt in v]

    @field_validator("answer")
    @classmethod
    def answer_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Answer cannot be empty.")
        return v.strip()


class QuizResponse(BaseModel):
    quiz: List[QuizQuestion]

    @field_validator("quiz")
    @classmethod
    def validate_quiz(cls, v):
        if len(v) < 5:
            raise ValueError(f"At least 5 quiz questions are required, got {len(v)}.")

        seen_questions = set()

        for q in v:
            # The answer must be one of the options. If not, fail so the
            # script retries, instead of silently corrupting the quiz.
            if q.answer not in q.options:
                raise ValueError(
                    f"Answer '{q.answer}' does not match any option for '{q.question}'."
                )

            key = q.question.lower()
            if key in seen_questions:
                raise ValueError(f"Duplicate question detected: '{q.question}'")
            seen_questions.add(key)

        return v


# -----------------------------
# combine_results.py output — what the C# backend deserializes
# -----------------------------

class FinalResponse(BaseModel):
    summary: str
    notes: List[Note]
    quiz: List[QuizQuestion]