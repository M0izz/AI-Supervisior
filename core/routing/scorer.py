"""
Deterministic routing scoring engine for AI Supervisor.
Evaluates agent capabilities, availability, and historical empirical reliability.
"""

from typing import Any, Dict, List, Optional, Tuple
from adapters.base import AgentAdapter
from adapters.models import AdapterAvailabilityStatus
from core.routing.models import RoutingCandidate, TaskRequirements


class RoutingScorer:
    """
    Deterministic capability matching and multi-factor scoring.
    Enforces strict eligibility gates before awarding preference and reliability points.
    """

    # Scoring constants
    BASE_CAPABILITY_POINTS = 10.0
    PREFERRED_CAPABILITY_POINTS = 2.0
    AVAILABILITY_POINTS = 2.0
    SUCCESS_WEIGHT = 1.0
    FAILURE_WEIGHT = -2.0
    HANDOFF_WEIGHT = -1.5
    INTERVENTION_WEIGHT = -1.0
    MAX_RELIABILITY_BOUND = 10.0
    MIN_RELIABILITY_BOUND = -10.0

    @classmethod
    async def evaluate_candidate(
        cls,
        agent_id: str,
        adapter: AgentAdapter,
        requirements: TaskRequirements,
        historical_metrics: Optional[Dict[str, Any]] = None,
    ) -> RoutingCandidate:
        """
        Evaluates a single adapter candidate against task requirements.
        Determines eligibility and computes a deterministic score breakdown.
        """
        caps = [str(c) for c in adapter.capabilities]
        metrics = historical_metrics or {}
        ineligibility_reasons: List[str] = []

        # 1. Exclusion Gate
        if agent_id in requirements.excluded_agent_ids:
            ineligibility_reasons.append(
                f"Agent '{agent_id}' is explicitly excluded from this routing request (e.g. failed source agent)."
            )

        # 2. Availability Gate
        try:
            avail = await adapter.check_availability()
            is_available = bool(avail.available)
            avail_status = avail.status.value
            if not is_available:
                ineligibility_reasons.append(
                    f"Agent '{agent_id}' is unavailable ({avail.status.value}): {avail.message}"
                )
        except Exception as e:
            is_available = False
            avail_status = AdapterAvailabilityStatus.UNAVAILABLE.value
            ineligibility_reasons.append(
                f"Availability check for agent '{agent_id}' raised exception: {e}"
            )

        # 3. Required Capabilities Gate
        missing_required = [
            c for c in requirements.required_capabilities if c not in caps
        ]
        if missing_required:
            ineligibility_reasons.append(
                f"Missing required capabilities: {missing_required}"
            )

        is_eligible = len(ineligibility_reasons) == 0

        # 4. Scoring Computation (only eligible candidates receive positive score)
        score_breakdown: Dict[str, float] = {}
        total_score = 0.0

        if is_eligible:
            # Base capability score for meeting 100% of required capabilities
            score_breakdown["capability_match"] = cls.BASE_CAPABILITY_POINTS

            # Preferred capabilities score
            matched_preferred = [
                c for c in requirements.preferred_capabilities if c in caps
            ]
            pref_score = len(matched_preferred) * cls.PREFERRED_CAPABILITY_POINTS
            score_breakdown["preferred_capability_match"] = pref_score

            # Availability score
            score_breakdown["availability"] = cls.AVAILABILITY_POINTS

            # Historical Reliability score (Cold start safe)
            successes = float(metrics.get("verified_successes", 0))
            failures = float(metrics.get("verification_failures", 0))
            handoffs = float(metrics.get("handoffs", 0))
            interventions = float(metrics.get("watchdog_interventions", 0))

            total_historical_events = successes + failures + handoffs + interventions
            if total_historical_events == 0:
                # Cold start: neutral score (Section 12)
                reliability_score = 0.0
            else:
                raw_rel = (
                    (successes * cls.SUCCESS_WEIGHT)
                    + (failures * cls.FAILURE_WEIGHT)
                    + (handoffs * cls.HANDOFF_WEIGHT)
                    + (interventions * cls.INTERVENTION_WEIGHT)
                )
                reliability_score = max(
                    cls.MIN_RELIABILITY_BOUND,
                    min(cls.MAX_RELIABILITY_BOUND, raw_rel),
                )
            score_breakdown["reliability"] = round(reliability_score, 2)

            total_score = round(sum(score_breakdown.values()), 2)
        else:
            score_breakdown["ineligible"] = 0.0

        # Construct concise evaluation summary
        if is_eligible:
            summary = (
                f"Eligible: meets {len(requirements.required_capabilities)} required capabilities; "
                f"matched {len(score_breakdown.get('preferred_capability_match', 0.0)) if isinstance(score_breakdown.get('preferred_capability_match'), list) else int(score_breakdown.get('preferred_capability_match', 0) / cls.PREFERRED_CAPABILITY_POINTS)} preferred; "
                f"reliability score {score_breakdown.get('reliability', 0.0):.1f}; total score {total_score:.1f}"
            )
        else:
            summary = f"Ineligible: {'; '.join(ineligibility_reasons)}"

        return RoutingCandidate(
            agent_id=agent_id,
            adapter_id=adapter.identity.adapter_id,
            capabilities=caps,
            availability=avail_status,
            is_available=is_available,
            is_eligible=is_eligible,
            ineligibility_reasons=ineligibility_reasons,
            score=total_score,
            score_breakdown=score_breakdown,
            historical_metrics=metrics,
            evaluation_summary=summary,
        )

    @classmethod
    def rank_candidates(
        cls, candidates: List[RoutingCandidate]
    ) -> List[RoutingCandidate]:
        """
        Sorts candidates by score with deterministic tie-breaking (Section 13):
        1. Higher score first
        2. Fewer verification failures
        3. Fewer handoffs
        4. Fewer unused capabilities (tighter fit)
        5. Stable lexicographical agent_id ordering
        """
        def sort_key(c: RoutingCandidate) -> Tuple[int, float, float, float, int, str]:
            # 1. Eligibility gate (1 for eligible, 0 for ineligible)
            elig_flag = 1 if c.is_eligible else 0
            # 2. Score
            score = c.score
            # 3. Failures (negated for descending sort)
            failures = -float(c.historical_metrics.get("verification_failures", 0))
            # 4. Handoffs (negated for descending sort)
            handoffs = -float(c.historical_metrics.get("handoffs", 0))
            # 5. Tightness of capabilities
            cap_count = -len(c.capabilities)
            # 6. Negative string for descending sort or invert in key
            return (elig_flag, score, failures, handoffs, cap_count, c.agent_id)

        # Python sort is stable; sort descending on metrics, ascending on agent_id
        # We can implement a clean custom comparator:
        return sorted(
            candidates,
            key=lambda c: (
                1 if c.is_eligible else 0,
                c.score,
                -float(c.historical_metrics.get("verification_failures", 0)),
                -float(c.historical_metrics.get("handoffs", 0)),
                -len(c.capabilities),
                # Lexicographical tie break: reverse order so reverse=True gives 'claude' before 'codex'
                "".join(chr(255 - ord(ch)) for ch in c.agent_id)
            ),
            reverse=True,
        )
