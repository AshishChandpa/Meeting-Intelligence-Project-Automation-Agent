"""Stage 2 node — Clarification Loop."""

from __future__ import annotations

import json
import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage

from agent.llm import complete_structured, complete_text
from agent.prompts.clarification_enhanced import (
    FOLLOWUP_SYSTEM,
    FOLLOWUP_USER,
    QUESTIONS_BY_CATEGORY_SYSTEM,
    QUESTIONS_FOR_HUMAN_SYSTEM,
    QUESTIONS_FOR_HUMAN_USER,
    QUESTIONS_SYSTEM,
    QUESTIONS_USER,
)
from agent.state import ClarificationQuestions, PipelineState

logger = logging.getLogger(__name__)


def generate_questions(state: PipelineState) -> dict:
    """Generate targeted clarification questions from the Stage 1 extraction."""
    messages = [
        {"role": "system", "content": QUESTIONS_SYSTEM},
        {
            "role": "user",
            "content": QUESTIONS_USER.format(
                transcript=state["raw_transcript"],
                extraction=json.dumps(state["extraction"], indent=2),
            ),
        },
    ]

    result: ClarificationQuestions = complete_structured(messages, schema=ClarificationQuestions)
    questions = [q.model_dump() for q in result.questions]

    logger.info("Generated %d clarification questions", len(questions))

    return {
        "questions": questions,
        "current_stage": "clarify",
        "messages": [
            AIMessage(
                content=(
                    f"I've generated {len(questions)} clarification questions based on "
                    "the gaps in your transcript. Answer each one, skip if not applicable, "
                    "or type 'done' when you're satisfied and ready for the Scope of Work."
                )
            )
        ],
    }


def process_answer(state: PipelineState) -> dict:
    """Process a user's answer to a clarification question.

    Expects the last HumanMessage to be in the format:
        "<question_id>: <answer>"   e.g. "q1: The OMS uses OAuth2"
    or:
        "<question_id>: skip <reason>"
    """
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        return {}

    raw = user_messages[-1].content.strip()
    questions = [dict(q) for q in state["questions"]]  # copy

    # Parse "q1: answer text" format
    question_id, _, answer_text = raw.partition(":")
    question_id = question_id.strip().lower()
    answer_text = answer_text.strip()

    # Find the matching question
    target = next((q for q in questions if q["id"] == question_id), None)
    if target is None:
        return {
            "messages": [
                AIMessage(content=f"Couldn't find question '{question_id}'. Use the format 'q1: your answer'.")
            ]
        }

    # Handle skip
    if answer_text.lower().startswith("skip"):
        target["status"] = "skipped"
        target["skip_reason"] = answer_text[4:].strip()
        return {
            "questions": questions,
            "messages": [AIMessage(content=f"Skipped question {question_id}.")],
        }

    # Mark answered
    target["status"] = "answered"
    target["answer"] = answer_text

    # Check if a follow-up is needed
    followup_messages = [
        {"role": "system", "content": FOLLOWUP_SYSTEM},
        {
            "role": "user",
            "content": FOLLOWUP_USER.format(
                question=target["question"],
                answer=answer_text,
                extraction=json.dumps(state["extraction"], indent=2),
            ),
        },
    ]
    followup_response = complete_text(followup_messages)

    # If the LLM generated a follow-up, add it as a new question
    if followup_response.strip().startswith("Follow-up:"):
        followup_text = followup_response.split("Follow-up:", 1)[1].strip()
        new_id = f"q{len(questions) + 1}"
        questions.append({
            "id": new_id,
            "question": followup_text,
            "context": f"Follow-up to {question_id}",
            "status": "open",
            "answer": "",
            "skip_reason": "",
        })
        reply = f"Answered {question_id}. Follow-up added: **{new_id}**: {followup_text}"
    else:
        reply = followup_response  # "Got it: ..."

    return {
        "questions": questions,
        "messages": [AIMessage(content=reply)],
    }


def generate_questions_for_human(state: PipelineState) -> dict:
    """Generate categorized questions specifically formatted for human review.

    This uses the enhanced QUESTIONS_FOR_HUMAN prompts to organize questions
    by category (Scope, Timeline, Technical, Budget, Team, Process) with
    clear impact statements.
    """
    # Extract unknowns and assumptions from the extraction
    extraction = state["extraction"]
    unknowns = extraction.get("unknowns", [])
    assumptions = [a for a in extraction.get("assumptions", []) if a.get("confidence") == "low"]

    messages = [
        {"role": "system", "content": QUESTIONS_FOR_HUMAN_SYSTEM},
        {
            "role": "user",
            "content": QUESTIONS_FOR_HUMAN_USER.format(
                project_name=extraction.get("project_name", "Unknown Project"),
                client_name=extraction.get("client_name", "Unknown Client"),
                extraction=json.dumps(extraction, indent=2),
                unknowns=json.dumps(unknowns, indent=2),
                assumptions=json.dumps(assumptions, indent=2),
            ),
        },
    ]

    human_questions = complete_text(messages)

    logger.info("Generated categorized questions for human review")

    return {
        "human_questions": human_questions,
        "messages": [
            AIMessage(
                content=(
                    "I've prepared targeted questions organized by category:\n\n"
                    f"{human_questions}\n\n"
                    "These questions will help clarify gaps before drafting the Scope of Work."
                )
            )
        ],
    }
