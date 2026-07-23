# A Negotiation-Aware Hybrid LLM Framework for Intent Interpretation and Service Discovery

This repository contains the dataset, implementation, and evaluation artifacts associated with a **negotiation-aware framework** for natural-language (NL) request interpretation and service discovery in cloud service composition.




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
│
├── code_implementation/
│   └── Python implementation of the framework
│
└── evaluation_results/
    └── Experimental results
```

