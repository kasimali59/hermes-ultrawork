"""Pure, deterministic routing policy for Hermes Ultrawork."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

POLICY_VERSION = "hermes-ultrawork-route-v1"
WorkKind = Literal["research", "architecture", "implementation", "integration", "qa", "reporting", "docs", "operations"]
RouteClass = Literal["architect_gate", "architecture", "large_decomposable", "difficult_integration", "qa", "reporting", "high_uncertainty_research", "small_bounded", "ordinary_low_risk"]

PROTECTED_TAGS = frozenset({"hardware_control", "firmware", "kernel", "ec", "wmi", "hid", "smbus", "privileged", "credentials", "secrets", "destructive", "publishing", "payment", "external_message", "security_boundary"})
PROTECTED_TERMS = ("credential", "api key", "secret", "password", "payment", "billing", "publish", "send message", "external message", "firmware", "kernel", "embedded controller", "hardware controller", "wmi", "hid", "smbus", "privileged", "sudo", "delete all", "drop table", "rm -rf")
WORK_KINDS = frozenset({"research", "architecture", "implementation", "integration", "qa", "reporting", "docs", "operations"})

@dataclass(frozen=True, slots=True)
class RoutingFacts:
    title: str
    body: str = ""
    work_kind: WorkKind = "implementation"
    estimated_files: int = 1
    acceptance_checks: int = 1
    independent_units: int = 1
    integration_boundaries: int = 0
    estimated_minutes: int = 10
    requested_tokens: int = 1000
    protected_tags: tuple[str, ...] = ()
    architecture_ambiguity: bool = False
    public_api_change: bool = False
    security_boundary: bool = False
    lifecycle_change: bool = False
    sqlite_change: bool = False
    provider_accounting_change: bool = False
    review_dispatch_change: bool = False
    cross_platform_change: bool = False
    uncertainty: Literal["low", "high"] = "low"
    open_questions: int = 0
    report_writer_healthy: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip(): raise ValueError("title must be a non-empty string")
        if not isinstance(self.body, str): raise TypeError("body must be a string")
        if self.work_kind not in WORK_KINDS: raise ValueError("unsupported work_kind")
        if self.uncertainty not in {"low", "high"}: raise ValueError("unsupported uncertainty")
        for name in ("estimated_files", "acceptance_checks", "independent_units", "integration_boundaries", "estimated_minutes", "requested_tokens", "open_questions"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0: raise ValueError(f"{name} must be a non-negative integer")
        for name in ("architecture_ambiguity", "public_api_change", "security_boundary", "lifecycle_change", "sqlite_change", "provider_accounting_change", "review_dispatch_change", "cross_platform_change"):
            if not isinstance(getattr(self, name), bool): raise TypeError(f"{name} must be a bool")
        if self.report_writer_healthy is not None and not isinstance(self.report_writer_healthy, bool): raise TypeError("report_writer_healthy must be bool or None")
        if not isinstance(self.protected_tags, tuple) or any(not isinstance(tag, str) for tag in self.protected_tags): raise TypeError("protected_tags must be a tuple of strings")
        if set(self.protected_tags) - PROTECTED_TAGS: raise ValueError("unsupported protected tag")

@dataclass(frozen=True, slots=True)
class RoutingDecision:
    policy_version: str
    route_class: RouteClass
    assignee: str | None
    reason_codes: tuple[str, ...]
    decompose: bool = False
    allow_paid_upgrade: bool = False


def _large(f: RoutingFacts) -> bool:
    return f.independent_units >= 3 or f.estimated_files >= 5 or f.acceptance_checks >= 8 or f.estimated_minutes > 30 or f.requested_tokens > 80000


def _integration(f: RoutingFacts) -> bool:
    return f.integration_boundaries >= 2 or f.work_kind == "integration" or f.lifecycle_change or f.sqlite_change or f.provider_accounting_change or f.review_dispatch_change or f.security_boundary or f.cross_platform_change


def _small(f: RoutingFacts) -> bool:
    return f.estimated_files <= 2 and f.acceptance_checks <= 5 and f.independent_units == 1 and f.integration_boundaries <= 1 and f.estimated_minutes <= 20 and f.requested_tokens <= 40000 and not f.protected_tags and f.open_questions == 0 and not f.architecture_ambiguity


def route_task(facts: RoutingFacts) -> RoutingDecision:
    if not isinstance(facts, RoutingFacts): raise TypeError("facts must be RoutingFacts")
    text = f"{facts.title}\n{facts.body}".casefold()
    if facts.protected_tags or any(term in text for term in PROTECTED_TERMS): return RoutingDecision(POLICY_VERSION, "architect_gate", None, ("protected_content",))
    if facts.open_questions or facts.work_kind == "architecture" or facts.architecture_ambiguity or facts.public_api_change or facts.security_boundary: return RoutingDecision(POLICY_VERSION, "architecture", "architect", ("architecture_gate",))
    if _large(facts): return RoutingDecision(POLICY_VERSION, "large_decomposable", "architect", ("large_decomposable",), True)
    if _integration(facts): return RoutingDecision(POLICY_VERSION, "difficult_integration", "engineering-lead", ("difficult_integration",))
    if facts.work_kind == "qa": return RoutingDecision(POLICY_VERSION, "qa", "qa-engineer", ("qa_specialist",))
    if facts.work_kind == "reporting" and facts.report_writer_healthy is True: return RoutingDecision(POLICY_VERSION, "reporting", "report-writer", ("report_writer_healthy",))
    if facts.work_kind == "reporting": return RoutingDecision(POLICY_VERSION, "ordinary_low_risk", "free-worker", ("report_writer_unhealthy_or_unknown",))
    if facts.work_kind == "research" and facts.uncertainty == "high": return RoutingDecision(POLICY_VERSION, "high_uncertainty_research", "researcher", ("high_uncertainty_research",))
    if _small(facts): return RoutingDecision(POLICY_VERSION, "small_bounded", "free-worker", ("small_bounded",))
    return RoutingDecision(POLICY_VERSION, "ordinary_low_risk", "free-worker", ("ordinary_low_risk",))
