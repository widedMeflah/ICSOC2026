from typing import Optional, List
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState


class RootState(MessagesState):
    """
    État global partagé entre tous les nœuds du graphe.
    """
    # Requête originale de l'utilisateur
    user_request: str = Field(default="", description="La requête brute de l'utilisateur")

    # Résultat du nœud d'interprétation
    interpreted_request: Optional[str] = Field(default=None, description="Requête reformulée/complétée")
    detected_conflicts: Optional[List[str]] = Field(default=None, description="Liste des conflits détectés")
    interpretation_complete: bool = Field(default=False, description="True si aucun conflit restant")

    # Contraintes de placement structurées (localisations + co-locations)
    placement_constraints: Optional[dict] = Field(
        default=None,
        description="Contraintes de placement structurées : node_placements, colocations, anti_colocations"
    )

    # Policies non-fonctionnelles structurées (coût, disponibilité, latence...)
    policies: Optional[List[dict]] = Field(
        default=None,
        description="Policies non-fonctionnelles structurées : liste de {type, value, targets}"
    )

    # Résultat du nœud de négociation
    negotiation_response: Optional[str] = Field(default=None, description="Propositions de la négociation")
    negotiation_round: int = Field(default=0, description="Nombre de tours de négociation effectués")

    # Résultat du nœud TOSCA
    tosca_template: Optional[str] = Field(default=None, description="Template TOSCA généré")

    # Résultat du discovery (offres candidates par node)
    candidates: Optional[dict] = Field(default=None, description="Offres candidates par node (discovery)")

    # Contrôle du flux
    error: Optional[str] = Field(default=None, description="Message d'erreur éventuel")
    # Résultat du nœud de relaxation
    relaxation_plans: Optional[List[dict]] = Field(default=None, description="Plans de relaxation proposés pour les conflits")