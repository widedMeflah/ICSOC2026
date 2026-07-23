"""
placement_utils.py
──────────────────
Représentation STRUCTURÉE du placement géographique.

Les contraintes relationnelles (co-location / anti-co-location) ne sont PAS
stockées ici : elles sont RÉSOLUES pendant l'interprétation (intersection des
localisations pour la co-location, séparation pour l'anti-co-location) et le
résultat est exprimé directement sous forme de localisations autorisées par nœud.

Ne subsiste donc qu'une notion : pour chaque nœud, l'ensemble des localisations
qu'il peut occuper (une seule si la résolution l'a réduite, plusieurs si un choix
multi-région reste légitime).

Conversion déterministe vers des policies Placement TOSCA-compatibles
(consommées par Jsontotosca.generate_tosca_yaml) + rendu lisible.

À placer à la racine du projet, à côté de root_state.py.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Modèles
# ─────────────────────────────────────────────────────────────────────────────
class LocationOption(BaseModel):
    """Une localisation possible : une région et/ou une zone de disponibilité."""
    region: Optional[str] = None
    availability_zone: Optional[str] = None


class NodePlacement(BaseModel):
    """Les localisations qu'un nœud PEUT occuper après résolution des contraintes."""
    node: str
    allowed_locations: List[LocationOption] = Field(default_factory=list)


class PlacementConstraints(BaseModel):
    """Conteneur du placement géographique d'une architecture (localisations par nœud)."""
    node_placements: List[NodePlacement] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_placement(placement) -> PlacementConstraints:
    """Accepte None / dict / PlacementConstraints et renvoie toujours un PlacementConstraints."""
    if isinstance(placement, PlacementConstraints):
        return placement
    if isinstance(placement, dict):
        try:
            return PlacementConstraints.model_validate(placement)
        except Exception:
            return PlacementConstraints()
    return PlacementConstraints()


def _loc_dict(loc) -> dict:
    """Normalise une localisation en dict {region?, availability_zone?} (champs vides retirés)."""
    if isinstance(loc, LocationOption):
        region, az = loc.region, loc.availability_zone
    elif isinstance(loc, dict):
        region, az = loc.get("region"), loc.get("availability_zone")
    else:
        return {}
    d = {}
    if region:
        d["region"] = region
    if az:
        d["availability_zone"] = az
    return d


def _loc_label(loc) -> str:
    """Libellé lisible d'une localisation, ex : 'eu-west-1 (eu-west-1a)' ou 'USA'."""
    d = _loc_dict(loc)
    if "region" in d and "availability_zone" in d:
        return f"{d['region']} ({d['availability_zone']})"
    return d.get("region") or d.get("availability_zone") or ""


# ─────────────────────────────────────────────────────────────────────────────
# Conversion structurée -> policies Placement (dicts attendus par Jsontotosca)
# ─────────────────────────────────────────────────────────────────────────────
def placement_to_policies(placement) -> List[dict]:
    """
    Construit la liste de policies Placement à partir du placement structuré.
    Règle "une policy par valeur distincte" : les nœuds qui partagent EXACTEMENT
    le même ensemble de localisations autorisées sont regroupés ; les autres ont
    chacun leur propre policy.
    """
    pc = _normalize_placement(placement)
    policies: List[dict] = []

    groups: dict = {}
    order: list = []
    for np_ in pc.node_placements:
        locs = [d for d in (_loc_dict(l) for l in np_.allowed_locations) if d]
        if not locs:
            continue
        key = tuple(sorted((l.get("region", ""), l.get("availability_zone", "")) for l in locs))
        if key not in groups:
            groups[key] = {"locations": locs, "nodes": []}
            order.append(key)
        if np_.node not in groups[key]["nodes"]:
            groups[key]["nodes"].append(np_.node)

    for i, key in enumerate(order, 1):
        nodes = groups[key]["nodes"]
        locs = groups[key]["locations"]
        pname = f"placement_{nodes[0]}" if len(nodes) == 1 else f"placement_group_{i}"
        policies.append({
            "name": pname,
            "type": "Placement",
            "targets": nodes,
            "properties": [{
                "name": "locations",
                "value": locs,
                "type": "list",
                "required": True,
                "description": "",
            }],
        })

    return policies


# ─────────────────────────────────────────────────────────────────────────────
# Rendu lisible (affichage Streamlit + requête augmentée)
# ─────────────────────────────────────────────────────────────────────────────
def render_placement(placement) -> str:
    """Rendu markdown lisible des localisations par nœud. '' si vide."""
    pc = _normalize_placement(placement)
    lines = []
    for np_ in pc.node_placements:
        labels = [lbl for lbl in (_loc_label(l) for l in np_.allowed_locations) if lbl]
        if labels:
            lines.append(f"- **{np_.node}** : {' ou '.join(labels)}")
    if not lines:
        return ""
    return "Localisations :\n" + "\n".join(lines)