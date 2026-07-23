import logging
import json as json_lib
import re
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, START, END

from root_state import RootState
from nodes.interpretation import build_interpretation_node
from nodes.relaxation import build_relaxation_node
from nodes.json_node import json_node
from Jsontotosca import generate_tosca_yaml
from placement_utils import placement_to_policies
from discovery import discover_candidates

logger = logging.getLogger(__name__)

NODE_INTERPRETATION = "interpretation"
NODE_RELAXATION     = "relaxation"
NODE_TOSCA          = "tosca"


def route_after_interpretation(state: RootState) -> Literal["relaxation", "tosca", "__end__"]:
    if state.get("error"):
        logger.warning("[Router] Erreur détectée, arrêt du flux.")
        return END
    if state.get("interpretation_complete"):
        logger.info("[Router] Aucun conflit → TOSCA")
        return NODE_TOSCA
    logger.info("[Router] Conflits détectés → Relaxation (interprétation)")
    return NODE_RELAXATION


def route_after_tosca(state: RootState) -> Literal["relaxation", "__end__"]:
    """After TOSCA + discovery: if one or more nodes have ZERO candidate offer,
    route to the relaxation node (discovery mode). Otherwise, end."""
    if state.get("error"):
        logger.warning("[Router] Erreur détectée après TOSCA, arrêt du flux.")
        return END
    candidates = state.get("candidates") or {}
    zero_nodes = [
        n for n in candidates.get("nodes", [])
        if n.get("candidate_count", 0) == 0
    ]
    if zero_nodes:
        logger.info("[Router] %d node(s) sans candidat → Relaxation (discovery)", len(zero_nodes))
        return NODE_RELAXATION
    logger.info("[Router] Tous les nodes ont au moins un candidat → fin.")
    return END


def _nf_policies_to_tosca(policies: list[dict]) -> list[dict]:
    """
    Convertit les policies non-fonctionnelles {type, value, targets}
    au format attendu par generate_tosca_yaml / convert_json_to_tosca.
    """
    TYPE_MAP = {
        "cost":         ("Cost",         "max_cost"),
        "availability": ("Availability", "availability"),
        "latency":      ("Latency",      "max_latency"),
    }
    result = []
    for i, p in enumerate(policies):
        ptype = (p.get("type") or "").lower().strip()
        value = p.get("value", "")
        targets = p.get("targets") or []

        tosca_type, prop_name = TYPE_MAP.get(ptype, (ptype.capitalize(), "value"))

        numeric_match = re.search(r"[\d.]+", str(value))
        prop_value = (
            float(numeric_match.group())
            if numeric_match and ptype in ("cost", "availability")
            else value
        )

        result.append({
            "name": f"{ptype}_policy_{i+1}",
            "type": tosca_type,
            "targets": targets,
            "properties": [{
                "name":        prop_name,
                "value":       prop_value,
                "type":        "float" if ptype in ("cost", "availability") else "string",
                "required":    True,
                "description": "",
            }],
        })
    return result


def build_graph(llm: BaseChatModel) -> StateGraph:

    def tosca_node(state: RootState) -> dict:
        result = json_node(state, llm)
        json_output = result.get("json_output")
        json_result = result.get("json_result")

        if not json_output:
            return {"tosca_template": None, "error": "Échec génération JSON."}

        try:
            data = json_lib.loads(json_result) if json_result else json_output.model_dump(mode="json")

            placement_policies = placement_to_policies(state.get("placement_constraints"))
            nf_policies_raw    = state.get("policies") or []
            nf_policies        = _nf_policies_to_tosca(nf_policies_raw)

            all_policies = placement_policies + nf_policies
            if all_policies:
                data["policies"] = all_policies

            tosca_yaml = generate_tosca_yaml(data)
        except Exception as exc:
            return {"tosca_template": None, "error": f"Erreur TOSCA : {exc}"}

        # ---- Discovery : offres candidates par node ----
        candidates = None
        try:
            candidates = discover_candidates(tosca_yaml)
        except Exception as exc:
            logger.warning("[Discovery] échec : %s", exc)

        return {"tosca_template": tosca_yaml, "candidates": candidates}

    builder = StateGraph(RootState)
    builder.add_node(NODE_INTERPRETATION, build_interpretation_node(llm))
    builder.add_node(NODE_RELAXATION,     build_relaxation_node(llm))
    builder.add_node(NODE_TOSCA,          tosca_node)

    builder.add_edge(START, NODE_INTERPRETATION)

    # Interprétation -> relaxation (conflits A/B) | tosca (aucun conflit) | fin
    builder.add_conditional_edges(
        NODE_INTERPRETATION,
        route_after_interpretation,
        {NODE_RELAXATION: NODE_RELAXATION, NODE_TOSCA: NODE_TOSCA, END: END},
    )

    # TOSCA + discovery -> relaxation (0 candidat) | fin
    builder.add_conditional_edges(
        NODE_TOSCA,
        route_after_tosca,
        {NODE_RELAXATION: NODE_RELAXATION, END: END},
    )

    # La relaxation (les deux modes) renvoie toujours ses plans puis termine ;
    # la boucle (choix utilisateur -> requête augmentée -> ré-exécution) est
    # pilotée côté UI (app.py).
    builder.add_edge(NODE_RELAXATION, END)

    return builder.compile()