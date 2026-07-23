from typing import List
from pydantic import BaseModel, Field


# ===========================================================================
# 1. INTERPRETATION RELAXATION  (type A / type B conflicts, BEFORE discovery)
#    -> unchanged, kept as-is.
# ===========================================================================
class RelaxationOption(BaseModel):
    """A concrete option to relax a given conflict."""
    strategy: str = Field(
        description="Short label for the strategy (e.g. 'Increase the budget', 'Reduce the sizing')."
    )
    actions: List[str] = Field(
        description="Concrete modifications to apply to the architecture to resolve the conflict."
    )
    impact: str = Field(
        description="Consequences / trade-offs of this option (what is gained or sacrificed)."
    )


class RelaxationPlan(BaseModel):
    """Set of relaxation options proposed for ONE conflict."""
    conflict_index: int = Field(
        description="Index (1-based) of the handled conflict, in the order of detected_conflicts."
    )
    conflict_summary: str = Field(
        description="One-sentence summary of the handled conflict."
    )
    options: List[RelaxationOption] = Field(
        description="One to three alternative options to resolve this conflict."
    )


class RelaxationOutput(BaseModel):
    """Structured output produced by the relaxation node (interpretation mode)."""
    plans: List[RelaxationPlan] = Field(
        default_factory=list,
        description="One plan per detected conflict. Empty list if there is no conflict to relax."
    )


# ===========================================================================
# 2. DISCOVERY RELAXATION  (0 candidate offer for one or more nodes, AFTER discovery)
#    -> brand new, dedicated schema. Does NOT reuse the schema above because the
#       inputs (per-node registry diagnosis) and the goal (explain why no offer
#       exists + offer registry-backed alternatives) are completely different.
# ===========================================================================
class DiscoveryRelaxationOption(BaseModel):
    """A concrete option to bring back at least one candidate offer for a node."""
    strategy: str = Field(
        description="Short label (e.g. 'Increase the budget', 'Change the region', "
                    "'Lower the CPU requirement', 'Change the provider')."
    )
    actions: List[str] = Field(
        description="Concrete changes to apply, using ONLY the achievable values provided "
                    "in the discovery diagnosis (e.g. 'Raise the budget to at least 150/month'). "
                    "Never invent a value that is not backed by a real offer."
    )
    impact: str = Field(
        description="Honest trade-off of this option (what is gained, what is sacrificed)."
    )


class DiscoveryRelaxationPlan(BaseModel):
    """Set of relaxation options proposed for ONE node that has zero candidate."""
    node_name: str = Field(
        description="Exact component name (node_name) coming from the discovery result."
    )
    service_type: str = Field(
        description="Service type of the node (compute, network, database, loadbalancer, "
                    "object_storage, block_storage)."
    )
    conflict_summary: str = Field(
        description="One plain, non-technical sentence: why this component has no offer."
    )
    options: List[DiscoveryRelaxationOption] = Field(
        description="One to three alternative options to make at least one offer available."
    )


class DiscoveryRelaxationOutput(BaseModel):
    """Structured output produced by the relaxation node (discovery mode)."""
    plans: List[DiscoveryRelaxationPlan] = Field(
        default_factory=list,
        description="One plan per node that has zero candidate. Empty list if every node matched."
    )