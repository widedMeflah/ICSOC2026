from models.json_request import JsonRequest
from langchain_core.messages import SystemMessage, HumanMessage
from root_state import RootState
from prompts.json_prompt import json_request_prompt
import json as json_lib
import re


_MAX_RETRIES = 3


def _parse_json_from_llm(raw_text: str) -> dict:
    """
    Extrait le JSON de la réponse brute du LLM,
    même si elle est entourée de balises ```json ... ``` ou ``` ... ```.
    """
    # 1) Essai direct
    try:
        return json_lib.loads(raw_text.strip())
    except Exception:
        pass

    # 2) Extraction depuis un bloc markdown ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if match:
        try:
            return json_lib.loads(match.group(1))
        except Exception:
            pass

    # 3) Extraction du premier { ... } trouvé dans le texte
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        try:
            return json_lib.loads(match.group(0))
        except Exception:
            pass

    raise ValueError(f"Impossible d'extraire un JSON valide de la réponse LLM : {raw_text[:200]}")


# -----------------------------------------------------------------------------
# Normalisation : le LLM produit parfois des dicts a la place de listes
# pour properties, capabilities, requirements et policies.
# On corrige ici avant model_validate.
# -----------------------------------------------------------------------------

def _normalize_properties(props) -> list:
    """
    Convertit properties en liste de Property-compatibles.
    Accepte :
      - None / [] -> []
      - list deja correcte -> inchangee (on normalise quand meme les items)
      - dict plat  {"num_cpus": 2, ...} -> [{"name": "num_cpus", "value": 2, ...}]
    """
    if not props:
        return []

    if isinstance(props, dict):
        result = []
        for k, v in props.items():
            if isinstance(v, dict):
                # ex: {"num_cpus": {"value": 2, "description": "..."}}
                item = {"name": k, "value": v.get("value"), "description": v.get("description", ""), "type": v.get("type", "string"), "required": v.get("required", False)}
            else:
                item = {"name": k, "value": v, "description": "", "type": "string", "required": False}
            result.append(item)
        return result

    if isinstance(props, list):
        normalized = []
        for item in props:
            if isinstance(item, dict):
                # S'assurer que les champs obligatoires de Property sont presents
                normalized.append({
                    "name":        item.get("name", ""),
                    "description": item.get("description", ""),
                    "type":        item.get("type", "string"),
                    "required":    item.get("required", False),
                    "value":       item.get("value"),
                })
            else:
                normalized.append(item)
        return normalized

    return []


def _normalize_capabilities(caps) -> list:
    """
    Convertit capabilities en liste de Capability-compatibles.
    Accepte :
      - None / [] -> []
      - list deja correcte -> on normalise quand meme les properties internes
      - dict {"host": {"valid_source_types": [...], "properties": {...}}}
            -> [{"name": "host", "valid_source_types": [...], "properties": [...]}]
    """
    if not caps:
        return []

    if isinstance(caps, dict):
        result = []
        for k, v in caps.items():
            if isinstance(v, dict):
                cap = {
                    "name": k,
                    "valid_source_types": v.get("valid_source_types", []),
                    "properties": _normalize_properties(v.get("properties", [])),
                }
            else:
                cap = {"name": k, "valid_source_types": [], "properties": []}
            result.append(cap)
        return result

    if isinstance(caps, list):
        normalized = []
        for cap in caps:
            if isinstance(cap, dict):
                normalized.append({
                    "name":               cap.get("name", ""),
                    "valid_source_types": cap.get("valid_source_types", []),
                    "properties":         _normalize_properties(cap.get("properties", [])),
                })
            else:
                normalized.append(cap)
        return normalized

    return []


def _normalize_requirements(reqs) -> list:
    """
    Convertit requirements en liste de requirement-compatibles.
    Accepte list ou dict.
    """
    if not reqs:
        return []

    if isinstance(reqs, dict):
        return [{"name": k, "node": v if isinstance(v, str) else v.get("node", "")}
                for k, v in reqs.items()]

    if isinstance(reqs, list):
        return reqs

    return []


def _normalize_policies(policies) -> list:
    """
    Convertit policies en liste de Policy-compatibles.
    Accepte :
      - None / [] -> []
      - list deja correcte -> on normalise quand meme les properties internes
      - dict {"placement_policy": {"type": ..., "targets": [...], "properties": {...}}}
            -> [{"name": "placement_policy", "type": ..., "targets": [...], "properties": [...]}]
    Note: la 'value' d'une property de policy peut etre un scalaire OU une liste
    (cas 'locations' du Placement) ; _normalize_properties la conserve telle quelle.
    """
    if not policies:
        return []

    if isinstance(policies, dict):
        result = []
        for k, v in policies.items():
            if isinstance(v, dict):
                result.append({
                    "name":       k,
                    "type":       v.get("type", ""),
                    "targets":    v.get("targets", []) or [],
                    "properties": _normalize_properties(v.get("properties", [])),
                })
            else:
                result.append({"name": k, "type": "", "targets": [], "properties": []})
        return result

    if isinstance(policies, list):
        normalized = []
        for pol in policies:
            if isinstance(pol, dict):
                normalized.append({
                    "name":       pol.get("name", ""),
                    "type":       pol.get("type", ""),
                    "targets":    pol.get("targets", []) or [],
                    "properties": _normalize_properties(pol.get("properties", [])),
                })
            else:
                normalized.append(pol)
        return normalized

    return []


def _normalize_node(node: dict) -> dict:
    """Normalise un noeud complet."""
    node["properties"]    = _normalize_properties(node.get("properties", []))
    node["capabilities"]  = _normalize_capabilities(node.get("capabilities", []))
    node["requirements"]  = _normalize_requirements(node.get("requirements", []))
    return node


def _normalize_json_data(data: dict) -> dict:
    """Normalise toute la structure JSON avant model_validate."""
    if "nodes" in data and isinstance(data["nodes"], list):
        data["nodes"] = [_normalize_node(n) for n in data["nodes"]]
    if "policies" in data:
        data["policies"] = _normalize_policies(data["policies"])
    return data


# -----------------------------------------------------------------------------

def json_node(state: RootState, llm) -> dict:
    interpreted_request = state.get("interpreted_request")  if isinstance(state, dict) else getattr(state, "interpreted_request", None)
    user_request        = state.get("user_request", "")     if isinstance(state, dict) else getattr(state, "user_request", "")

    request_to_convert = interpreted_request or user_request

    print(f"\n[JSON] Generation JSON: '{request_to_convert[:60]}...'")

    base_messages = [
        SystemMessage(content=json_request_prompt),
        HumanMessage(content=f"<request>{request_to_convert}</request>")
    ]

    json_output  = None
    json_result  = None
    last_error   = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            if attempt == 1:
                messages = base_messages
            else:
                correction_hint = (
                    f"Your previous response caused this error: {last_error}. "
                    "Return ONLY a raw JSON object (no markdown, no ```json``` fences). "
                    "CRITICAL FORMAT RULES for every node:\n"
                    "- 'properties' must be a LIST of objects: "
                    "[{\"name\": \"num_cpus\", \"description\": \"...\", \"type\": \"integer\", \"required\": false, \"value\": 2}]\n"
                    "- 'capabilities' must be a LIST of objects with 'name' (string), "
                    "'valid_source_types' (list of strings), and 'properties' (list as above)\n"
                    "- 'requirements' must be a LIST of objects: [{\"name\": \"host\", \"node\": \"MyVM\"}]\n"
                    "- NEVER use a dict/object for 'properties', 'capabilities', or 'requirements'\n"
                    "- 'policies' (top-level, optional) must be a LIST of objects: "
                    "[{\"name\": \"placement_policy\", \"type\": \"Placement\", \"targets\": [\"my_vm\"], "
                    "\"properties\": [{\"name\": \"locations\", \"value\": [{\"region\": \"UK\"}], "
                    "\"type\": \"list\", \"required\": true, \"description\": \"\"}]}]\n"
                    "- 'nodes' must contain at least one complete node object."
                )
                messages = base_messages + [HumanMessage(content=correction_hint)]

            print(f"[JSON] Tentative {attempt}/{_MAX_RETRIES}...")

            # -- Appel brut --
            raw_response = llm.invoke(messages)
            raw_text = raw_response.content if hasattr(raw_response, "content") else str(raw_response)
            print(f"[JSON] Reponse brute (300 chars) : {raw_text[:300]}\n")

            # -- Parse manuel du JSON --
            data = _parse_json_from_llm(raw_text)

            # -- Normalisation dict -> list (properties / capabilities / requirements / policies) --
            data = _normalize_json_data(data)

            # -- Validation : nodes doit exister et ne pas etre vide --
            if not data.get("nodes"):
                raise ValueError("Le JSON parse ne contient pas de noeuds ('nodes' vide ou absent)")

            # -- Conversion en objet Pydantic JsonRequest --
            json_output = JsonRequest.model_validate(data)

            if not json_output.nodes:
                raise ValueError("JsonRequest.nodes est vide apres model_validate")

            print(f"[JSON] Tentative {attempt} reussie - {len(json_output.nodes)} noeuds, "
                  f"{len(json_output.policies or [])} policies")

            # Reserialise proprement (enums -> strings via mode='json')
            json_result = json_lib.dumps(
                json_output.model_dump(mode="json"), ensure_ascii=False, indent=2
            )
            break

        except Exception as e:
            last_error = str(e)
            print(f"[JSON] Tentative {attempt} echouee : {last_error[:150]}")
            if attempt == _MAX_RETRIES:
                print(f"[JSON] Echec apres {_MAX_RETRIES} tentatives")
                json_output = None
                json_result = json_lib.dumps(
                    {"description": "Erreur de generation JSON", "nodes": [], "policies": []},
                    ensure_ascii=False, indent=2
                )

    # NB: ce retour est consomme EN INTERNE par nodes/tosca.py (build_tosca_node),
    # pas directement par le graphe -- donc des cles non declarees dans RootState
    # ne posent aucun probleme ici.
    return {
        "json_output":         json_output,
        "json_result":         json_result,
        "interpreted_request": interpreted_request,
        "user_request":        user_request,
    }