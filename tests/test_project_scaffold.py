from research_assistant.planner import build_cltv_research_plan


def test_cltv_research_plan_has_required_blocks() -> None:
    plan = build_cltv_research_plan()

    assert plan.topic == "CLTV in foreign banks"
    assert "banking_use_cases" in plan.blocks
    assert len(plan.queries) >= 5

