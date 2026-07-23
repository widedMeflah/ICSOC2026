from typing import List, Literal
from pydantic import BaseModel, Field

from placement_utils import PlacementConstraints


class Conflict(BaseModel):
    """Un conflit détecté dans l'architecture."""

    type: Literal["A", "B"] = Field(
        description="'A' = requête vs limitation inhérente du paradigme cloud ; "
                    "'B' = deux contraintes utilisateur mutuellement insatisfiables."
    )
    components: List[str] = Field(
        description="Noms des composants impliqués."
    )
    conflicting_constraints: str = Field(
        description="Les propriétés/valeurs/policies précises en tension."
    )
    explanation: str = Field(
        description="Une à deux phrases expliquant pourquoi elles ne peuvent coexister."
    )


class NonFunctionalPolicy(BaseModel):
    """
    Une policy non-fonctionnelle explicitement énoncée par l'utilisateur
    (coût, disponibilité, latence, ...). Représentation générique.
    """
    type: str = Field(
        description="Le type de policy en minuscules : 'cost', 'availability', 'latency', "
                    "ou tout autre type non-fonctionnel explicitement énoncé."
    )
    value: str = Field(
        description="La valeur telle qu'énoncée, avec son unité : "
                    "ex '0.01 USD/month', '99.999%', '10 ms'."
    )
    targets: List[str] = Field(
        default_factory=list,
        description="Noms des composants concernés par la policy (doivent exister dans la prose)."
    )


class InterpretationOutput(BaseModel):
    """Structured output produit par le nœud d'interprétation."""

    interpreted_request: str = Field(
        description="Un seul paragraphe fluide décrivant l'architecture complète "
                    "(nom, valeurs de propriétés, relations). Aucun en-tête, liste, "
                    "JSON, ni information de conflit ni de placement dans ce champ."
    )
    detected_conflicts: List[Conflict] = Field(
        default_factory=list,
        description="Une entrée par conflit détecté. Liste vide si aucun."
    )
    placement: PlacementConstraints = Field(
        default_factory=PlacementConstraints,
        description="Contraintes de placement STRUCTURÉES extraites de la requête : "
                    "localisations alternatives par nœud (node_placements), groupes "
                    "co-localisés (colocations) et groupes à localisations différentes "
                    "(anti_colocations). Listes vides si aucun placement n'est exprimé. "
                    "Ce champ est le SEUL endroit où le placement est enregistré ; il ne "
                    "doit jamais apparaître dans interpreted_request."
    )
    policies: List[NonFunctionalPolicy] = Field(
        default_factory=list,
        description="Policies non-fonctionnelles STRUCTURÉES explicitement énoncées par "
                    "l'utilisateur (coût, disponibilité, latence, ...). Une entrée par policy, "
                    "avec son type, sa valeur et les composants concernés. Liste VIDE si "
                    "l'utilisateur n'énonce aucune policy. Ne jamais inventer de policy. "
                    "Ce champ assure que ces contraintes ne sont pas perdues entre les tours."
    )