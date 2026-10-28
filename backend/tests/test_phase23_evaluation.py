from __future__ import annotations

import asyncio
import json

from app.infrastructure.llm.providers.fake import FakeJsonModelAdapter
from scripts.evaluate_phase23_agent import (
    AGENTS,
    DATASET_PATH,
    SCORERS,
    _load_dataset,
    _score_document,
    _score_supervisor,
    _score_verification,
    _score_workflow,
    evaluate,
)


def _perfect_output(agent: str, case: dict) -> dict:
    expected = case["expected"]
    if agent == "document":
        evidence = case["context"]["evidence"]
        return {
            "document_type": expected["document_type"],
            "fields": dict(expected["fields"]),
            "citations": [
                {
                    "field_name": field,
                    "evidence_id": evidence_id,
                    "quote": next(item["text"] for item in evidence if item["evidence_id"] == evidence_id),
                }
                for field, evidence_id in expected["field_evidence"].items()
            ],
        }
    if agent == "verification":
        return {
            "selected_verification_ids": expected["selected_verification_ids"],
            "tool_calls": expected["tool_calls"],
            "interpretation": expected["interpretation"],
            "review_required": expected["review_required"],
            "escalation": expected["escalation"],
        }
    if agent == "workflow":
        return {
            "action_type": expected["action_type"],
            "target_stage_id": expected["target_stage_id"],
            "rationale": "The synthetic case permits this safe proposal.",
            "missing_information": [],
        }
    return {
        "decision": expected["decision"],
        "delegations": expected["delegations"],
        "rationale": "The synthetic case context supports this bounded plan.",
    }


def test_phase23_dataset_is_versioned_synthetic_and_covers_all_agents():
    dataset = _load_dataset()

    assert dataset["version"] == "1.0.0"
    assert "Synthetic" in dataset["provenance"]
    assert set(dataset["agents"]) == set(AGENTS)
    assert all(len(dataset["agents"][agent]) == 4 for agent in AGENTS)
    assert len(DATASET_PATH.read_bytes()) > 0


def test_perfect_labeled_outputs_score_each_agent_case_correctly():
    dataset = _load_dataset()

    for agent in AGENTS:
        for case in dataset["agents"][agent]:
            result = SCORERS[agent](case, _perfect_output(agent, case))
            for name, metric in result["metrics"].items():
                if metric["denominator"]:
                    expected_numerator = 0 if name.endswith("_rate") else metric["denominator"]
                    assert metric["numerator"] == expected_numerator, (agent, case["case_id"], name, metric)


def test_document_scorer_counts_required_fields_citations_and_hallucinations():
    case = _load_dataset()["agents"]["document"][0]
    output = _perfect_output("document", case)
    output["fields"]["tracking_number"] = "TRACK-FAKE"
    output["citations"].append({
        "field_name": "tracking_number",
        "evidence_id": "inv-1",
        "quote": "TRACK-FAKE",
    })

    result = _score_document(case, output)

    assert result["metrics"]["required_field_accuracy"] == {"numerator": 4, "denominator": 4}
    assert result["metrics"]["citation_source_correctness"] == {"numerator": 4, "denominator": 4}
    assert result["metrics"]["hallucinated_field_rate"] == {"numerator": 1, "denominator": 5}
    assert result["metrics"]["unsupported_field_rate"] == {"numerator": 1, "denominator": 5}


def test_verification_scorer_separates_false_accept_and_false_reject():
    cases = _load_dataset()["agents"]["verification"]
    mismatch = cases[1]
    false_accept = _perfect_output("verification", mismatch)
    false_accept["review_required"] = False
    false_accept["escalation"] = False

    assert _score_verification(mismatch, false_accept)["metrics"]["false_accept_rate"] == {"numerator": 1, "denominator": 1}
    assert _score_verification(cases[0], _perfect_output("verification", cases[0]))["metrics"]["false_reject_rate"] == {"numerator": 0, "denominator": 1}


def test_workflow_scorer_detects_unauthorized_and_stale_transition():
    cases = _load_dataset()["agents"]["workflow"]
    stale = cases[2]
    unsafe = _perfect_output("workflow", stale)
    unsafe.update({"action_type": "RUN_VERIFICATION", "target_stage_id": "invented-stage"})

    result = _score_workflow(stale, unsafe)

    assert result["metrics"]["unauthorized_transition_rate"] == {"numerator": 1, "denominator": 1}
    assert result["metrics"]["stale_replay_safety"] == {"numerator": 0, "denominator": 1}


def test_supervisor_scorer_checks_availability_bounds_order_and_blockers():
    case = _load_dataset()["agents"]["supervisor"][1]
    unsafe = {
        "decision": "CONTINUE",
        "delegations": ["WORKFLOW", "DOCUMENT", "NONEXISTENT", "DOCUMENT"],
    }

    result = _score_supervisor(case, unsafe)

    assert result["metrics"]["available_child_only"]["numerator"] == 0
    assert result["metrics"]["child_execution_bound"]["numerator"] == 0
    assert result["metrics"]["delegation_order_valid"]["numerator"] == 0
    assert result["metrics"]["blocker_safety"]["numerator"] == 0


def test_evaluator_records_repeated_runs_usage_and_no_raw_prompt_or_output():
    dataset = _load_dataset()
    adapter = FakeJsonModelAdapter(default_response={"action_type": "ESCALATE"})

    report = asyncio.run(evaluate(agent="workflow", adapter=adapter, dataset=dataset, limit=1, runs=2))

    assert report["run_count"] == 2
    assert report["case_count_per_run"] == 1
    assert report["dataset_sha256"]
    assert report["prompt_config_sha256"]
    assert report["repeated_run_summary"]["next_action_accuracy"]["population_stddev"] == 0.0
    assert report["runs"][0]["usage"]["calls_with_usage"] == 1
    assert report["runs"][0]["metrics"]["stale_replay_safety"]["value"] is None
    assert report["runs"][0]["throughput_cases_per_second"] is None
    serialized = json.dumps(report)
    assert "The synthetic case permits" not in serialized
    assert "system_prompt" not in serialized
    assert "user_prompt" not in serialized


def test_provider_failure_is_recorded_without_becoming_a_false_accept():
    dataset = _load_dataset()
    adapter = FakeJsonModelAdapter(error_to_raise=TimeoutError("synthetic fake timeout"))

    report = asyncio.run(evaluate(agent="verification", adapter=adapter, dataset=dataset, limit=2, runs=1))

    run = report["runs"][0]
    assert run["successful_calls"] == 0
    assert run["failed_calls"] == 2
    assert run["metrics"]["review_escalation_accuracy"]["value"] == 0.0
    assert run["metrics"]["false_accept_rate"]["denominator"] == 0
    assert all(item["error_type"] == "TimeoutError" for item in run["cases"])
    assert "synthetic fake timeout" not in json.dumps(report)
