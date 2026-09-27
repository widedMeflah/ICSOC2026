# A Negotiation-Aware Hybrid LLM Framework for Intent Interpretation and Service Discovery

This repository contains the dataset, implementation, and evaluation artifacts of a **negotiation-aware framework** for natural-language (NL) request interpretation and service discovery in cloud service composition.

The framework refines high-level and incomplete NL requests, dynamically detects conflicts, structures the request as a provider-independent TOSCA template, and retrieves compliant provider offers through deterministic matching against real cloud catalogs (AWS, Azure, GCP). Conflicts detected during interpretation, and requirements that prove unsatisfiable during discovery, are resolved through an iterative natural-language negotiation with the user.

This repository accompanies the paper:

Wided Meflah, Hayet Brabra and Walid Gaaloul, *A Negotiation-Aware Hybrid LLM Framework for Intent Interpretation and Service Discovery*. ICSOC 2026: International Conference on Service-Oriented Computing.

## Repository Structure

```text
ICSOC2026/
├── dataset/
│   └── The 70 natural-language requests used for evaluation, described by
│       seven columns: (1) identifier, (2) NL request, (3) request form
│       (complete low-level, incomplete low-level, business-oriented),
│       (4) conflict type (conflict-free, cloud-paradigm, user-requirement,
│       discovery), (5) ground-truth conflicts, (6) admissible relaxations,
│       (7) near-miss flag.
│
├── code_implementation/
│   └── Python implementation of the framework
│
└── evaluation_results/
    └── Experimental results
```

## Citation

If you use this dataset or code, please cite:

```bibtex
@inproceedings{meflah2026negotiation,
  title     = {A Negotiation-Aware Hybrid LLM Framework for Intent Interpretation and Service Discovery},
  author    = {Meflah, Wided and Brabra, Hayet and Gaaloul, Walid},
  booktitle = {International Conference on Service-Oriented Computing (ICSOC)},
  year      = {2026},
  publisher = {Springer}
}
```
