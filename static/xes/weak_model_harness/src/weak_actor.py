from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import sys

XES_ROOT = Path(__file__).resolve().parents[2]
if str(XES_ROOT) not in sys.path:
    sys.path.insert(0, str(XES_ROOT))

from .cards import PromptLadderCard, ResponseProtocol, RiskCard, ScaffoldBudget, StudentState, TaskState
from .weak_llm_client import WeakOpenAICompatClient


WEAK_ACTOR_ANSWER_PROMPT = """
You are a weak student solver inside a scaffolded math student harness.
You are not a teacher and you are not a strong expert solver.

Object meanings:
- student_state: this student's stable math capability boundary.
- task_state: this item's required knowledge, operations, and format demands.
- scaffold_budget: the maximum amount of help the harness is allowed to give this student on this item.
- prompt_ladder: released hints up to the allowed support level; these hints reduce burden but do not solve the item.
- risk_card: likely pitfalls and self-check targets; these are warnings, not target mistakes.
- response_protocol: final output boundary.

Important boundary:
- Do NOT predict what result the harness wants.
- Do NOT imitate a preassigned correct/wrong label.
- Use the released support only as help for starting, organizing, and checking.
- The final answer must still be your own weak-student attempt under this support.
- Do not turn into a polished expert solver.
- Do not use help beyond response_protocol.max_support_level.

Difficulty calibration:
- task_state.perceived_difficulty is the harness difficulty label for this item.
- If task_state.difficulty_anchor_context is present, it contains real XES easy/medium/hard anchor items.
- Use these anchors only to calibrate how hard the item should feel for this student.
- Do not copy anchor answers or anchor wording.

Task:
- Read the item.
- First try independently using prompt_ladder.level0_instruction.
- Then use only the hints already released up to the allowed support level.
- If you still cannot fully solve, produce the best bounded student-like attempt instead of hallucinating an expert derivation.
- `predicted_answer` must contain only the answer itself.
- `student_response` must be plain text only. Do not use LaTeX, markdown, backslashes, or line breaks.
- If `response_protocol.response_style` is `just_answer`, set `student_response` exactly equal to `predicted_answer`.
- If `response_protocol.answer_mode` is `option_letter_only`, `predicted_answer` must be exactly one of A/B/C/D.
- Keep explanation minimal. Put optional short wording only in `student_response`.
- Output JSON only.

Return exactly:
{
  "predicted_answer": "string",
  "student_response": "string",
  "used_support_level": "L0|L1|L2|L3",
  "support_trace": ["short string"]
}
"""


WEAK_ACTOR_ANSWER_RETRY_PROMPT = """

Protocol correction:
- Your previous answer violated the structured output boundary.
- Regenerate from scratch.
- `predicted_answer` must be answer-only.
- If `response_protocol.answer_mode` is `option_letter_only`, output exactly one letter from A/B/C/D.
- `used_support_level` must be one of L0/L1/L2/L3 and must not exceed response_protocol.max_support_level.
- `student_response` must be plain text with no LaTeX, no markdown, no backslashes, and no line breaks.
- If response style is `just_answer`, `student_response` must exactly equal `predicted_answer`.
- Keep any optional short wording in `student_response`, not in `predicted_answer`.
"""


def generate_answer_with_weak_model(
    *,
    student_state: StudentState,
    task_state: TaskState,
    scaffold_budget: ScaffoldBudget,
    prompt_ladder: PromptLadderCard,
    risk_card: RiskCard,
    response_protocol: ResponseProtocol,
    question_text: str,
    options: dict[str, str],
    llm_client: WeakOpenAICompatClient,
) -> dict[str, object]:
    payload = {
        "student_state": asdict(student_state),
        "task_state": asdict(task_state),
        "scaffold_budget": asdict(scaffold_budget),
        "prompt_ladder": asdict(prompt_ladder),
        "risk_card": asdict(risk_card),
        "response_protocol": asdict(response_protocol),
        "question_text": question_text,
        "options": options,
    }
    prompts = [
        WEAK_ACTOR_ANSWER_PROMPT,
        WEAK_ACTOR_ANSWER_PROMPT + WEAK_ACTOR_ANSWER_RETRY_PROMPT,
    ]
    last_error = None
    for attempt_index, system_prompt in enumerate(prompts, start=1):
        parsed = llm_client.chat_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False),
        )
        predicted_answer = str(parsed.get("predicted_answer", "")).strip()
        student_response = str(parsed.get("student_response", "")).strip()
        used_support_level = str(parsed.get("used_support_level", "")).strip() or "L0"
        support_trace_raw = parsed.get("support_trace", [])
        if not isinstance(support_trace_raw, list):
            support_trace_raw = [str(support_trace_raw)]
        support_trace = [str(item).strip() for item in support_trace_raw if str(item).strip()]
        if (
            response_protocol.answer_mode == "option_letter_only"
            and predicted_answer.upper() not in {"A", "B", "C", "D"}
        ):
            last_error = parsed
            continue
        if predicted_answer and student_response:
            return {
                "predicted_answer": predicted_answer,
                "student_response": student_response,
                "used_support_level": used_support_level,
                "support_trace": support_trace,
                "attempt_count": attempt_index,
            }
        last_error = parsed
    raise ValueError(f"weak actor answer output cannot satisfy protocol after retry: {last_error}")
