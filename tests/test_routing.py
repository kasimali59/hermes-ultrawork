import pytest
from routing import RoutingFacts, route_task


def test_small_work_uses_free_worker():
    d = route_task(RoutingFacts("Fix a typo"))
    assert (d.route_class, d.assignee) == ("small_bounded", "free-worker")
    assert d.allow_paid_upgrade is False


def test_large_work_is_architect_owned_and_decomposable():
    d = route_task(RoutingFacts("Build feature", estimated_files=5))
    assert (d.route_class, d.assignee, d.decompose) == ("large_decomposable", "architect", True)


def test_integration_uses_engineering_lead():
    d = route_task(RoutingFacts("Wire lifecycle", lifecycle_change=True))
    assert d.assignee == "engineering-lead"


def test_qa_uses_qa_profile():
    assert route_task(RoutingFacts("Run regression", work_kind="qa")).assignee == "qa-engineer"


def test_protected_content_never_goes_to_worker():
    d = route_task(RoutingFacts("Rotate API credentials"))
    assert d.route_class == "architect_gate"
    assert d.assignee is None


def test_high_uncertainty_research_uses_researcher():
    assert route_task(RoutingFacts("Explore unknown API", work_kind="research", uncertainty="high")).assignee == "researcher"


def test_reporting_requires_explicit_health():
    assert route_task(RoutingFacts("Write report", work_kind="reporting")).assignee == "free-worker"
    assert route_task(RoutingFacts("Write report", work_kind="reporting", report_writer_healthy=True)).assignee == "report-writer"


@pytest.mark.parametrize("kwargs", [{"estimated_files": -1}, {"work_kind": "unknown"}, {"architecture_ambiguity": None}, {"protected_tags": ("unknown",)}])
def test_invalid_facts_fail_closed(kwargs):
    with pytest.raises((TypeError, ValueError)):
        RoutingFacts("bad", **kwargs)
