"""
Interface Streamlit pour le système de génération de templates TOSCA.
Lancement : streamlit run main.py
"""
from dotenv import load_dotenv
load_dotenv()

import logging
import sys
import os
import re
from enum import Enum
from typing import Any

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from langchain_openai    import ChatOpenAI
from langchain_mistralai import ChatMistralAI
from langchain_groq      import ChatGroq

from agent_graph import build_graph
from placement_utils import render_placement

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class LLMType(str, Enum):
    OPEN_AI = "openai"
    GROQ_AI = "groq"
    MISTRAL = "mistral"

LLM_CONFIGS: dict[str, dict[str, Any]] = {
    "GPT_4o_mini":   {"model_name": "gpt-4o-mini",             "llm_type": LLMType.OPEN_AI, "temperature": 0},
    "Groq_gpt120b":  {"model_name": "openai/gpt-oss-120b",     "llm_type": LLMType.GROQ_AI, "temperature": 0, "max_retries": 2},
    "mistral_7b":    {"model_name": "open-mistral-7b",         "llm_type": LLMType.MISTRAL, "temperature": 0},
    "mistral-large-2512":  {"model_name": "mistral-large-2512",      "llm_type": LLMType.MISTRAL, "temperature": 0},
    "llama_3.3_70b": {"model_name": "llama-3.3-70b-versatile", "llm_type": LLMType.GROQ_AI, "temperature": 0},
}

# ---------------------------------------------------------------------------
# Helpers LLM / graphe
# ---------------------------------------------------------------------------
def create_llm(config_key: str):
    cfg = LLM_CONFIGS[config_key]
    llm_type = cfg["llm_type"]
    kwargs = {k: v for k, v in cfg.items() if k != "llm_type"}

    if llm_type == LLMType.OPEN_AI:
        return ChatOpenAI(**kwargs)
    if llm_type == LLMType.GROQ_AI:
        return ChatGroq(**kwargs)
    if llm_type == LLMType.MISTRAL:
        return ChatMistralAI(**kwargs)
    raise ValueError(f"Unsupported LLMType: {llm_type}")


@st.cache_resource(show_spinner=False)
def get_graph(config_key: str):
    llm = create_llm(config_key)
    return build_graph(llm)


# ---------------------------------------------------------------------------
# Helpers de rendu
# ---------------------------------------------------------------------------
CONFLICT_TYPE_LABELS = {
    "A": "Cloud paradigm incompatibility",
    "B": "Conflicting user constraints",
}

def render_conflict(i: int, conflict) -> str:
    """Rend un conflit de façon propre, qu'il soit un dict structuré ou du texte libre."""
    if isinstance(conflict, dict):
        parts = []
        ctype = conflict.get("type")
        if ctype:
            label = CONFLICT_TYPE_LABELS.get(str(ctype).upper(), f"Type {ctype}")
            parts.append(f"**{label}**")
        comps = conflict.get("components")
        if comps:
            comps = ", ".join(comps) if isinstance(comps, list) else comps
            parts.append(f"_Components_: {comps}")
        if conflict.get("conflicting_constraints"):
            parts.append(f"_Constraints_: {conflict['conflicting_constraints']}")
        if conflict.get("explanation"):
            parts.append(conflict["explanation"])
        body = " — ".join(parts)
    else:
        body = re.sub(r"^\s*\d+[\.\)]\s*[-•]?\s*", "", str(conflict)).strip()
    return f"**{i}.** {body}"


def render_relaxation(plans) -> None:
    """Affiche les plans de relaxation avec une numérotation GLOBALE des options."""
    n = 0
    for plan in plans:
        idx = plan.get("conflict_index")
        summary = plan.get("conflict_summary", "")
        st.markdown(f"**Conflict {idx}** — {summary}" if idx else f"**{summary}**")
        for opt in plan.get("options", []):
            n += 1
            st.markdown(f"- **[{n}]** *{opt.get('strategy', '')}*")
            for a in opt.get("actions", []):
                st.markdown(f"    - {a}")
            if opt.get("impact"):
                st.markdown(f"    - _Impact_: {opt['impact']}")


def render_policies(policies) -> str:
    """Rendu markdown lisible des policies non-fonctionnelles. '' si vide."""
    if not policies:
        return ""
    lines = []
    for p in policies:
        if not isinstance(p, dict):
            continue
        ptype = (p.get("type") or "").strip()
        value = (p.get("value") or "").strip()
        targets = p.get("targets") or []
        targets = ", ".join(targets) if isinstance(targets, list) else str(targets)
        label = f"- **{ptype or 'policy'}**: {value}".rstrip()
        if targets:
            label += f"  _(on {targets})_"
        lines.append(label)
    if not lines:
        return ""
    return "Policies:\n" + "\n".join(lines)


def render_zero_candidate_warning(final_state) -> list:
    """Retourne la liste des nodes discovery sans candidat (candidate_count == 0)."""
    cands = final_state.get("candidates") or {}
    return [n for n in cands.get("nodes", []) if n.get("candidate_count", 0) == 0]


def flatten_options(plans) -> list[dict]:
    """Aplati toutes les options dans l'ORDRE D'AFFICHAGE (= numéros montrés à l'utilisateur)."""
    flat = []
    for plan in plans:
        for opt in plan.get("options", []):
            flat.append({
                "conflict_index":   plan.get("conflict_index"),
                "conflict_summary": plan.get("conflict_summary", ""),
                "strategy":         opt.get("strategy", ""),
                "actions":          opt.get("actions", []),
                "impact":           opt.get("impact", ""),
            })
    return flat


def build_augmented_request(original_request: str, interpreted: str,
                            placement_text: str, policies_text: str, chosen: list[dict]) -> str:
    """Construit la nouvelle requête : requête originale + architecture + placement + policies + option(s)."""
    lines = []
    for o in chosen:
        ci = o.get("conflict_index")
        prefix = f"(conflict {ci}) " if ci else ""
        act = "; ".join(o.get("actions", []))
        lines.append(f"- {prefix}{o.get('strategy', '')}: {act}")
    block = "\n".join(lines)

    placement_part = ""
    if placement_text:
        placement_part = (
            "Current geographic placement (regions / availability zones) that MUST be preserved "
            "unless a relaxation below changes it:\n"
            f"<placement>\n{placement_text}\n</placement>\n\n"
        )

    policies_part = ""
    if policies_text:
        policies_part = (
            "Current non-functional policies (cost / availability / latency) that MUST be preserved "
            "unless a relaxation below changes them:\n"
            f"<policies>\n{policies_text}\n</policies>\n\n"
        )

    return (
        "Here is the ORIGINAL user request. It contains constraints (such as geographic "
        "regions, availability zones, cost, latency, co-location) that MUST be preserved unless a "
        "relaxation below explicitly changes them:\n"
        f"<original_request>\n{original_request}\n</original_request>\n\n"
        "Here is the interpreted architecture so far:\n"
        f"<interpreted>\n{interpreted}\n</interpreted>\n\n"
        f"{placement_part}"
        f"{policies_part}"
        "The user has chosen to apply the following relaxation(s) to resolve the detected "
        "conflict(s). These relaxations are CUMULATIVE: they include every relaxation already "
        "applied in previous rounds and they all remain in force. Apply ALL of them, keep every "
        "other original constraint intact, then redo the interpretation, the placement resolution "
        "and the conflict detection:\n"
        f"{block}"
    )


# ---------------------------------------------------------------------------
# État de session
# ---------------------------------------------------------------------------
def init_state():
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("graph_state", None)
    st.session_state.setdefault("llm_key", "GPT_4o_mini")
    st.session_state.setdefault("awaiting_choice", False)
    st.session_state.setdefault("pending_options", [])
    st.session_state.setdefault("relax_round", 0)
    st.session_state.setdefault("original_request", "")
    st.session_state.setdefault("applied_relaxations", [])


def reset_conversation():
    st.session_state.messages = []
    st.session_state.graph_state = None
    st.session_state.awaiting_choice = False
    st.session_state.pending_options = []
    st.session_state.relax_round = 0
    st.session_state.original_request = ""
    st.session_state.applied_relaxations = []


# ---------------------------------------------------------------------------
# Exécution du graphe + affichage
# ---------------------------------------------------------------------------
def run_and_display(user_request: str):
    graph = get_graph(st.session_state.llm_key)

    initial_state = {
        "user_request":            user_request,
        "messages":                [],
        "interpreted_request":     None,
        "detected_conflicts":      None,
        "interpretation_complete": False,
        "placement_constraints":   None,
        "policies":                None,
        "relaxation_plans":        None,
        "negotiation_response":    None,
        "negotiation_round":       st.session_state.relax_round,
        "tosca_template":          None,
        "candidates":              None,
        "error":                   None,
    }

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Analyzing..."):
            try:
                final_state = graph.invoke(initial_state)
            except Exception as exc:
                logger.exception("Graph error: %s", exc)
                st.error(f"Unexpected error: {exc}")
                return

        st.session_state.graph_state = final_state

        # --- Erreur ---
        if final_state.get("error"):
            content = f"❌ {final_state['error']}"
            st.error(content)
            st.session_state.messages.append({
                "role": "assistant", "type": "error", "content": content, "avatar": "🤖",
            })
            st.session_state.awaiting_choice = False
            return

        interpreted = final_state.get("interpreted_request")
        if not interpreted:
            st.warning("No interpretation produced.")
            st.session_state.awaiting_choice = False
            return

        # --- Section 1 — Architecture interprétée ---
        st.info("🔍 Interpreted architecture")
        st.markdown(interpreted)
        st.session_state.messages.append({
            "role": "assistant", "type": "interpreted", "content": interpreted, "avatar": "🤖",
        })

        # --- Section 1bis — Placement structuré (localisations) ---
        placement_text = render_placement(final_state.get("placement_constraints"))
        if placement_text:
            st.info("📍 Placement")
            st.markdown(placement_text)
            st.session_state.messages.append({
                "role": "assistant", "type": "placement", "content": placement_text, "avatar": "🤖",
            })

        # --- Section 1ter — Policies non-fonctionnelles (coût / dispo / latence) ---
        policies_text = render_policies(final_state.get("policies"))
        if policies_text:
            st.info("⚙️ Policies")
            st.markdown(policies_text)
            st.session_state.messages.append({
                "role": "assistant", "type": "policies", "content": policies_text, "avatar": "🤖",
            })

        # --- Section 2 — Rapport de conflits d'interprétation (A/B) ---
        conflicts = final_state.get("detected_conflicts") or []
        zero_nodes = render_zero_candidate_warning(final_state)
        if conflicts:
            st.warning("⚠️ Conflicts detected")
            for i, conflict in enumerate(conflicts, 1):
                st.markdown(render_conflict(i, conflict))
            st.session_state.messages.append({
                "role": "assistant", "type": "conflicts", "content": conflicts, "avatar": "🤖",
            })
        elif zero_nodes:
            # Pas de conflit d'interprétation, mais la discovery n'a trouvé
            # aucune offre pour un ou plusieurs nodes.
            names = ", ".join(n.get("node_name", "?") for n in zero_nodes)
            msg = f"⚠️ No candidate offer found for: {names}"
            st.warning(msg)
            st.session_state.messages.append({
                "role": "assistant", "type": "hint", "content": msg, "avatar": "🤖",
            })
        else:
            st.success("✅ No conflicts detected.")
            st.session_state.messages.append({
                "role": "assistant", "type": "conflicts", "content": [], "avatar": "🤖",
            })

        # --- Section 3 — TOSCA généré (présent dès que la discovery a tourné) ---
        tosca = final_state.get("tosca_template")
        if tosca:
            st.success("✅ TOSCA template generated")
            st.code(tosca, language="yaml")
            st.session_state.messages.append({
                "role": "assistant", "type": "tosca", "content": tosca, "avatar": "🤖",
            })

        # --- Section 4 — Offres candidates (discovery) ---
        candidates = final_state.get("candidates")
        if candidates:
            st.info("🛰️ Candidate offers (discovery)")
            st.json(candidates)
            st.session_state.messages.append({
                "role": "assistant", "type": "candidates", "content": candidates, "avatar": "🤖",
            })

        # --- Section 5 — Plans de relaxation ---
        # (conflits d'interprétation A/B OU discovery 0 candidat : même format)
        plans = final_state.get("relaxation_plans") or []
        if plans:
            st.info("🛠️ Proposed relaxation plans")
            render_relaxation(plans)
            st.session_state.messages.append({
                "role": "assistant", "type": "relaxation", "content": plans, "avatar": "🤖",
            })

            flat = flatten_options(plans)
            st.session_state.pending_options = flat
            st.session_state.awaiting_choice = True

            hint = ("👉 Pick one or more options by typing their number(s) "
                    f"(between 1 and {len(flat)}, e.g. `1` or `1,3`).")
            st.markdown(hint)
            st.session_state.messages.append({
                "role": "assistant", "type": "hint", "content": hint, "avatar": "🤖",
            })
            return

        # --- Plus aucun plan en attente → fin du cycle ---
        st.session_state.awaiting_choice = False
        st.session_state.pending_options = []


def handle_choice(text: str):
    """Traite le choix d'option(s) de l'utilisateur et relance l'interprétation."""
    flat = st.session_state.get("pending_options") or []
    nums = [int(x) for x in re.findall(r"\d+", text)]
    valid = [k for k in nums if 1 <= k <= len(flat)]

    if not valid:
        with st.chat_message("assistant", avatar="🤖"):
            msg = f"⚠️ Invalid number. Enter a number between 1 and {len(flat)}."
            st.warning(msg)
        st.session_state.messages.append({
            "role": "assistant", "type": "hint", "content": msg, "avatar": "🤖",
        })
        return  # on reste en attente d'un choix valide

    chosen = [flat[k - 1] for k in valid]

    # Accumuler les relaxations de TOUS les tours, pas seulement celles du tour courant,
    # sinon les relaxations précédentes sont perdues quand on ré-affirme la requête originale
    # comme base autoritaire (un conflit déjà résolu pourrait alors réapparaître).
    st.session_state.applied_relaxations.extend(chosen)
    all_chosen = st.session_state.applied_relaxations

    gs = st.session_state.graph_state or {}
    interpreted = gs.get("interpreted_request", "")
    original = st.session_state.get("original_request", "")             # requête d'origine
    placement_text = render_placement(gs.get("placement_constraints"))  # placement courant
    policies_text = render_policies(gs.get("policies"))                 # policies courantes
    augmented = build_augmented_request(original, interpreted, placement_text, policies_text, all_chosen)

    st.session_state.relax_round += 1
    st.session_state.awaiting_choice = False
    st.session_state.pending_options = []

    run_and_display(augmented)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TOSCA Generator",
    page_icon="🏗️",
    layout="wide",
)

init_state()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Settings")

    selected_llm = st.selectbox(
        "LLM model",
        options=list(LLM_CONFIGS.keys()),
        index=list(LLM_CONFIGS.keys()).index(st.session_state.llm_key),
        help="Choose the language model to use.",
    )

    if selected_llm != st.session_state.llm_key:
        st.session_state.llm_key = selected_llm
        reset_conversation()
        st.rerun()

    st.caption(f"🔧 `{LLM_CONFIGS[selected_llm]['model_name']}`")
    st.divider()

    if st.button("🗑️ New conversation", use_container_width=True):
        reset_conversation()
        st.rerun()

# ---------------------------------------------------------------------------
# Zone principale
# ---------------------------------------------------------------------------
st.title("🏗️ TOSCA Template Generator")
st.caption("Describe your infrastructure in natural language.")

# Affichage de l'historique
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar=msg.get("avatar")):
        if msg.get("type") == "interpreted":
            st.info("🔍 Interpreted architecture")
            st.markdown(msg["content"])
        elif msg.get("type") == "placement":
            st.info("📍 Placement")
            st.markdown(msg["content"])
        elif msg.get("type") == "policies":
            st.info("⚙️ Policies")
            st.markdown(msg["content"])
        elif msg.get("type") == "conflicts":
            conflicts = msg["content"]
            if conflicts:
                st.warning("⚠️ Conflicts detected")
                for i, conflict in enumerate(conflicts, 1):
                    st.markdown(render_conflict(i, conflict))
            else:
                st.success("✅ No conflicts detected.")
        elif msg.get("type") == "relaxation":
            st.info("🛠️ Proposed relaxation plans")
            render_relaxation(msg["content"])
        elif msg.get("type") == "tosca":
            st.success("✅ TOSCA template generated")
            st.code(msg["content"], language="yaml")
        elif msg.get("type") == "candidates":
            st.info("🛰️ Candidate offers (discovery)")
            st.json(msg["content"])
        elif msg.get("type") == "error":
            st.error(msg["content"])
        else:  # hint et messages normaux
            st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Input utilisateur
# ---------------------------------------------------------------------------
placeholder = (
    "Type the number of your chosen option (e.g. 1 or 1,3)..."
    if st.session_state.awaiting_choice
    else "Describe your cloud infrastructure..."
)
user_input = st.chat_input(placeholder)

if user_input:
    st.session_state.messages.append({
        "role": "user", "content": user_input, "avatar": "👤",
    })
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    if st.session_state.awaiting_choice:
        handle_choice(user_input)
    else:
        st.session_state.relax_round = 0
        st.session_state.original_request = user_input   # on fige la requête d'origine
        st.session_state.applied_relaxations = []        # nouveau cycle → on repart à zéro
        run_and_display(user_input)