from __future__ import annotations

import json
import os
from pathlib import Path
import sys

XES_ROOT = Path(__file__).resolve().parents[1]
if str(XES_ROOT) not in sys.path:
    sys.path.insert(0, str(XES_ROOT))

from src.llm_client import LLMConfig, OpenAICompatClient
from src.problem_profile import build_problem_requirement_profile
from src.student_model import build_student_model

from weak_model_harness.src.compile_cards import (
    compile_response_space,
    compile_student_state,
    compile_task_state,
)
from weak_model_harness.src.weak_actor import (
    generate_answer_with_weak_model,
    resolve_student_item_state_with_weak_model,
)
from weak_model_harness.src.weak_llm_client import WeakLLMConfig, WeakOpenAICompatClient


def main() -> None:
    root = XES_ROOT
    xes_root = root
    weak_api_key = os.environ.get("BAILIAN_API_KEY", "").strip()
    if not weak_api_key:
        raise ValueError("missing env BAILIAN_API_KEY for weak model smoke demo")

    with (xes_root / "outputs" / "student_conditioned_benchmark_full_20260506_qwen9501_v2" / "run_20260506_112237" / "benchmark_students.jsonl").open("r", encoding="utf-8") as file:
        row = json.loads(file.readline())

    with (root.parent.parent / "XES3G5M" / "metadata" / "questions.json").open("r", encoding="utf-8") as file:
        questions = json.load(file)

    enhanced_persona = row["enhanced_persona"]
    from src.data_loading import PersonaRecord, MathAnchorProfile, MathTaskCapabilityAnchor

    persona = PersonaRecord(
        student_id=enhanced_persona["student_id"],
        grade=enhanced_persona["grade"],
        academic_level=enhanced_persona["academic_level"],
        strong_subjects=enhanced_persona["strong_subjects"],
        weak_subjects=enhanced_persona["weak_subjects"],
        learning_profile_text=enhanced_persona["learning_profile_text"],
        math_anchor_profile=(
            MathAnchorProfile(**enhanced_persona["math_anchor_profile"])
            if enhanced_persona["math_anchor_profile"] is not None
            else None
        ),
        math_task_capability_anchor=(
            MathTaskCapabilityAnchor(**enhanced_persona["math_task_capability_anchor"])
            if enhanced_persona["math_task_capability_anchor"] is not None
            else None
        ),
    )

    strong_client = OpenAICompatClient(
        LLMConfig(
            base_url="https://ai-notebook-inspire.sii.edu.cn/ws-9dcc0e1f-80a4-4af2-bc2f-0e352e7b17e6/project-b795c114-135a-40db-b3d0-19b60f25237b/user-c6264b38-46a1-4bb6-a3a7-1db39453f6f8/vscode/a8d28302-91b1-48a6-aa64-fd7cc9ec78a7/42ee0f16-fe96-4181-9765-4e16e74567f7/proxy/9501/v1",
            model="qwen",
            api_key="dummy",
            timeout_s=120.0,
            temperature=0.2,
            max_tokens=1200,
            response_format_json=True,
        )
    )
    weak_client = WeakOpenAICompatClient(
        WeakLLMConfig(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen3-1.7b",
            api_key=weak_api_key,
            timeout_s=120.0,
            temperature=0.0,
            max_tokens=256,
            response_format_json=False,
            enable_thinking=False,
        )
    )

    student_model = build_student_model(persona, llm_client=strong_client)
    test_qid = row["test"][0][0]
    q = questions[test_qid]
    profile = build_problem_requirement_profile(
        question_text=q["content"],
        options=q.get("options") or {},
        question_type=q["type"],
        llm_client=strong_client,
    )

    student_state = compile_student_state(student_model)
    task_state = compile_task_state(str(test_qid), str(q["type"]), profile)
    student_item_state = resolve_student_item_state_with_weak_model(
        student_state=student_state,
        task_state=task_state,
        llm_client=weak_client,
    )
    response_space = compile_response_space(task_state, student_item_state)
    answer_output = generate_answer_with_weak_model(
        student_state=student_state,
        task_state=task_state,
        student_item_state=student_item_state,
        response_space=response_space,
        question_text=q["content"],
        options=q.get("options") or {},
        llm_client=weak_client,
    )
    print(
        json.dumps(
            {
                "student_state": student_state.__dict__,
                "task_state": task_state.__dict__,
                "student_item_state": student_item_state.__dict__,
                "response_space": response_space.__dict__,
                "answer_output": answer_output,
                "gold_answer": q["answer"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
