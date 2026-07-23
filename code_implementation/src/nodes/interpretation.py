import logging
import re
from langchain_core.language_models import BaseChatModel

from root_state import RootState
from models.interpretation import InterpretationOutput, Conflict
from prompts.interpretation import INTERPRETATION_FIRST_TEMPLATE

logger = logging.getLogger(__name__)


def _coerce_conflict(block: str) -> Conflict:
    """Construit un Conflict à partir d'un bloc de texte libre (fallback)."""
    def grab(field):
        m = re.search(rf"{field}\s*[:\-]\s*(.+)", block, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    t = grab("type").strip(' "\'').upper()
    t = t if t in ("A", "B") else "B"

    comps_raw = grab("components")
    comps = [c.strip() for c in re.split(r"[,;]", comps_raw) if c.strip()]

    return Conflict(
        type=t,
        components=comps,
        conflicting_constraints=grab("conflicting_constraints") or grab("constraints"),
        explanation=grab("explanation") or block.strip(),
    )


def _parse_fallback(text: str) -> InterpretationOutput:
    """
    Parse manuellement la sortie texte du LLM quand with_structured_output échoue.
    Note : le placement structuré n'est pas récupérable depuis le texte libre ;
    il reste vide dans ce cas (PlacementConstraints par défaut).
    """
    # Section 1 : accepte "Section 1" OU "Interpreted Architecture"
    sec1 = re.search(
        r"(?:Section\s*1|Interpreted\s+Architecture)\b.*?\n(.*?)"
        r"(?=Section\s*2|Conflict\s+Report|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    interpreted = sec1.group(1).strip() if sec1 else text.strip()

    # Section 2 : accepte "Section 2" OU "Conflict Report"
    sec2 = re.search(
        r"(?:Section\s*2|Conflict\s+Report)\b.*?\n(.*)",
        text, re.DOTALL | re.IGNORECASE,
    )
    conflicts_text = sec2.group(1).strip() if sec2 else ""

    # Cas explicite "no conflicts detected"
    if re.search(r"no conflicts?\s+detected", conflicts_text, re.IGNORECASE):
        return InterpretationOutput(interpreted_request=interpreted, detected_conflicts=[])

    # Parsing raté ou section conflits vide : liste vide, sans rien forcer d'autre.
    if not conflicts_text:
        return InterpretationOutput(interpreted_request=interpreted, detected_conflicts=[])

    # Split qui gère AUSSI le 1er élément (début de chaîne) → plus de "1. 1."
    raw = re.split(r"(?:^|\n)\s*\d+[\.\)]\s+", conflicts_text)
    blocks = [b.strip() for b in raw if b.strip()]
    return InterpretationOutput(
        interpreted_request=interpreted,
        detected_conflicts=[_coerce_conflict(b) for b in blocks],
    )


def build_interpretation_node(llm: BaseChatModel):
    structured_chain = INTERPRETATION_FIRST_TEMPLATE | llm.with_structured_output(
        InterpretationOutput
    )
    raw_chain = INTERPRETATION_FIRST_TEMPLATE | llm

    def interpretation_node(state: RootState) -> dict:
        logger.info(
            "[Interpretation] tour=%d  request='%s'",
            state.get("negotiation_round", 0),
            state.get("user_request", "")[:80],
        )

        try:
            result: InterpretationOutput = structured_chain.invoke({
                "user_request": state["user_request"],
            })

        except Exception as exc:
            logger.warning(
                "[Interpretation] structured_output échoué (%s), fallback texte.", exc
            )
            failed_text = _extract_failed_generation(exc)
            if not failed_text:
                try:
                    failed_text = raw_chain.invoke(
                        {"user_request": state["user_request"]}
                    ).content
                except Exception as exc2:
                    logger.exception("[Interpretation] Erreur fallback : %s", exc2)
                    return {
                        "error": f"Erreur dans le nœud d'interprétation : {exc2}",
                        "interpretation_complete": False,
                    }

            try:
                result = _parse_fallback(failed_text)
            except Exception as exc3:
                logger.exception("[Interpretation] Erreur parsing fallback : %s", exc3)
                return {
                    "error": f"Erreur parsing fallback : {exc3}",
                    "interpretation_complete": False,
                }

        conflicts = result.detected_conflicts or []
        complete = len(conflicts) == 0          # <-- source unique de vérité

        # Placement structuré (peut être vide). On le sérialise en dict pour l'état.
        placement = result.placement.model_dump() if getattr(result, "placement", None) else {}

        # Policies non-fonctionnelles structurées (coût, dispo, latence...). Liste de dicts.
        policies = [p.model_dump() for p in (getattr(result, "policies", None) or [])]

        logger.info(
            "[Interpretation] complete=%s  conflicts=%d  placements=%d  policies=%d",
            complete, len(conflicts), len((placement or {}).get("node_placements", [])), len(policies)
        )

        return {
            "interpreted_request":     result.interpreted_request,
            "detected_conflicts":      [c.model_dump() for c in conflicts],
            "interpretation_complete": complete,
            "placement_constraints":   placement,
            "policies":                policies,
        }

    return interpretation_node


def _extract_failed_generation(exc: Exception) -> str | None:
    """
    Groq renvoie le texte généré dans le champ failed_generation de l'erreur 400.
    On tente de l'extraire depuis le message d'exception.
    """
    try:
        import json
        msg = str(exc)
        json_match = re.search(r"\{.*\}", msg, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("error", {}).get("failed_generation")
    except Exception:
        pass
    return None