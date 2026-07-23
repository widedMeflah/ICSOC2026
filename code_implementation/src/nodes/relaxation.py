import json
import logging

from langchain_core.language_models import BaseChatModel

from root_state import RootState
from models.relaxation import RelaxationOutput, DiscoveryRelaxationOutput
from prompts.relaxation import RELAXATION_TEMPLATE, DISCOVERY_RELAXATION_TEMPLATE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _format_conflicts(conflicts: list) -> str:
    """Interpretation conflicts (dicts) -> readable text for the prompt."""
    if not conflicts:
        return "Aucun conflit."
    lines = []
    for i, c in enumerate(conflicts, 1):
        if isinstance(c, dict):
            ctype = c.get("type", "?")
            comps = c.get("components") or []
            comps = ", ".join(comps) if isinstance(comps, list) else str(comps)
            constraints = c.get("conflicting_constraints", "")
            expl = c.get("explanation", "")
        else:
            ctype, comps, constraints, expl = "?", "", "", str(c)
        lines.append(
            f"{i}. [type {ctype}] components: {comps} | "
            f"constraints: {constraints} | explanation: {expl}"
        )
    return "\n".join(lines)


def _format_discovery_conflicts(zero_nodes: list) -> str:
    """Discovery failures (nodes with 0 candidate) -> readable text for the prompt.

    Includes the registry-backed achievable values already computed by
    `analyze_conflicts` (region / provider / sla / cost / specs), so the LLM only
    has to phrase them for the user, never to invent numbers.
    """
    if not zero_nodes:
        return "No failing node."

    blocks = []
    for i, n in enumerate(zero_nodes, 1):
        name = n.get("node_name", "?")
        stype = n.get("service_type", "?")
        funnel = n.get("filter_funnel") or {}
        ca = n.get("conflict_analysis") or {}

        reason = funnel.get("reason") or ca.get("resolution") or "no candidate offer."
        ctype = ca.get("conflict_type", ca.get("status", "?"))

        lines = [
            f"### Node {i}: {name} ({stype})",
            f"reason: {reason}",
            f"conflict_type: {ctype}",
        ]

        sat = ca.get("criteria_individually_satisfiable")
        if sat:
            lines.append(f"criteria_individually_satisfiable: {sat}")

        opts = ca.get("options") or []
        if opts:
            lines.append("options (registry-backed, achievable values — DO NOT invent others):")
            for o in opts:
                detail = o.get("detail", "")
                crit = o.get("criterion") or o.get("spec") or o.get("action") or "?"
                data = {k: v for k, v in o.items() if k != "detail"}
                lines.append(
                    f"  - [{crit}] {detail} | data: {json.dumps(data, ensure_ascii=False)}"
                )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _disco_to_common_plans(disco_plans: list) -> list:
    """Convert DiscoveryRelaxationPlan dumps into the common `relaxation_plans`
    shape expected by the UI (conflict_index / conflict_summary / options).
    This is what lets app.py reuse the exact same numbered-option mechanism."""
    common = []
    for i, p in enumerate(disco_plans, 1):
        node = p.get("node_name", "?")
        stype = p.get("service_type", "?")
        summary = f"{node} ({stype}) — {p.get('conflict_summary', '')}".strip(" —")
        common.append({
            "conflict_index": i,
            "conflict_summary": summary,
            "options": [
                {
                    "strategy": o.get("strategy", ""),
                    "actions": o.get("actions", []),
                    "impact": o.get("impact", ""),
                }
                for o in p.get("options", [])
            ],
        })
    return common


# ---------------------------------------------------------------------------
# Node builder — ONE node, TWO modes: interpretation vs discovery
# ---------------------------------------------------------------------------
def build_relaxation_node(llm: BaseChatModel):
    interp_structured = RELAXATION_TEMPLATE | llm.with_structured_output(RelaxationOutput)
    interp_raw        = RELAXATION_TEMPLATE | llm
    disco_structured  = DISCOVERY_RELAXATION_TEMPLATE | llm.with_structured_output(DiscoveryRelaxationOutput)
    disco_raw         = DISCOVERY_RELAXATION_TEMPLATE | llm

    # ---- mode 2 : discovery relaxation (0 candidate for one or more nodes) ----
    def _discovery(state: RootState, zero_nodes: list) -> dict:
        logger.info("[Relaxation/discovery] %d node(s) sans candidat.", len(zero_nodes))
        inputs = {
            "user_request":        state["user_request"],
            "interpreted_request": state.get("interpreted_request", ""),
            "discovery_conflicts": _format_discovery_conflicts(zero_nodes),
        }
        try:
            result: DiscoveryRelaxationOutput = disco_structured.invoke(inputs)
            plans = _disco_to_common_plans([p.model_dump() for p in result.plans])
        except Exception as exc:
            logger.warning("[Relaxation/discovery] structured_output échoué (%s), fallback texte.", exc)
            try:
                raw = disco_raw.invoke(inputs).content
            except Exception as exc2:
                logger.exception("[Relaxation/discovery] Erreur fallback : %s", exc2)
                return {"error": f"Erreur dans le nœud de relaxation (discovery) : {exc2}"}
            plans = [{
                "conflict_index": 0,
                "conflict_summary": "Plans de relaxation discovery (format brut)",
                "options": [{"strategy": "raw", "actions": [raw.strip()], "impact": ""}],
            }]
        logger.info("[Relaxation/discovery] %d plan(s) proposé(s).", len(plans))
        return {"relaxation_plans": plans}

    # ---- mode 1 : interpretation relaxation (type A / type B conflicts) ----
    def _interpretation(state: RootState, conflicts: list) -> dict:
        logger.info(
            "[Relaxation/interpretation] tour=%d  conflits=%d",
            state.get("negotiation_round", 0), len(conflicts),
        )
        inputs = {
            "user_request":        state["user_request"],
            "interpreted_request": state.get("interpreted_request", ""),
            "conflicts":           _format_conflicts(conflicts),
        }
        try:
            result: RelaxationOutput = interp_structured.invoke(inputs)
            plans = [p.model_dump() for p in result.plans]
        except Exception as exc:
            logger.warning("[Relaxation/interpretation] structured_output échoué (%s), fallback texte.", exc)
            try:
                raw = interp_raw.invoke(inputs).content
            except Exception as exc2:
                logger.exception("[Relaxation/interpretation] Erreur fallback : %s", exc2)
                return {"error": f"Erreur dans le nœud de relaxation : {exc2}"}
            plans = [{
                "conflict_index": 0,
                "conflict_summary": "Plans de relaxation (format brut)",
                "options": [{"strategy": "raw", "actions": [raw.strip()], "impact": ""}],
            }]
        logger.info("[Relaxation/interpretation] %d plan(s) proposé(s).", len(plans))
        return {"relaxation_plans": plans}

    # ---- dispatch ----
    def relaxation_node(state: RootState) -> dict:
        candidates = state.get("candidates") or {}
        zero_nodes = [
            n for n in candidates.get("nodes", [])
            if n.get("candidate_count", 0) == 0
        ]

        # Discovery relaxation is only reachable AFTER tosca/discovery, i.e. once
        # `candidates` is populated and at least one node has zero offer.
        if zero_nodes:
            return _discovery(state, zero_nodes)

        # Otherwise: interpretation relaxation (type A / type B conflicts).
        conflicts = state.get("detected_conflicts") or []
        if not conflicts:
            logger.info("[Relaxation] Aucun conflit, nœud ignoré.")
            return {"relaxation_plans": []}
        return _interpretation(state, conflicts)

    return relaxation_node