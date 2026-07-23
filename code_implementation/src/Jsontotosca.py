"""
Jsontotosca.py
Module pour convertir le JSON (nodes + policies) en TOSCA YAML.
"""

import json
import yaml
import re


def add_all_missing_commas(json_str: str) -> str:
    """Repare un JSON malforme en inserant les virgules manquantes (heuristique)."""
    lines = json_str.split("\n")
    fixed_lines = []
    for i in range(len(lines)):
        line = lines[i].rstrip()
        if i < len(lines) - 1:
            next_line = lines[i + 1].strip()
            if ":" in line and not line.endswith((",", "{", "[")) and (
                next_line.startswith('"')
                or next_line.startswith("{")
                or re.match(r"\d+:\{", next_line)
            ):
                line += ","
        fixed_lines.append(line)
    result = "\n".join(fixed_lines)
    result = result.replace("NULL", "null")
    result = re.sub(r"\b\d+:\{", "{", result)
    result = re.sub(r"\}\s*\{", "},\n{", result)
    result = re.sub(r'("description":"[^"]+")(\s*"nodes")', r"\1,\2", result)
    return result


def parse_json(json_text: str) -> dict:
    """Parse un JSON, avec reparation de virgules en secours."""
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        fixed = add_all_missing_commas(json_text)
        return json.loads(fixed)


# -----------------------------------------------------------------------------
# Mapping type court (cote LLM/JSON) -> type TOSCA complet (cote YAML)
# -----------------------------------------------------------------------------
POLICY_TYPE_MAP = {
    "Placement":    "acme.policies.Placement",
    "Availability": "acme.policies.Availability",
    "Latency":      "acme.policies.Latency",
    "Cost":         "acme.policies.Cost",
}


def convert_json_to_tosca(data: dict) -> dict:
    """
    Convertit le JSON (nodes + policies) en structure TOSCA YAML.
    """
    tosca = {
        "tosca_definitions_version": "tosca_simple_yaml_1_3",
        "description": data.get("description", ""),

        "node_types": {
            "computeWithblocNetwork": {
                "derived_from": "tosca.nodes.Compute",
                "requirements": [
                    {"network_link": {"capability": "tosca.capabilities.network.Linkable",
                                      "node": "tosca.nodes.network.Network",
                                      "occurrences": [1, 'UNBOUNDED']}},
                    {"bloc_attachement": {"capability": "tosca.capabilities.Attachment",
                                          "node": "tosca.nodes.Storage.BlockStorage",
                                          "occurrences": [1, 'UNBOUNDED']}},
                ],
            },
            "computeWithnetwork": {
                "derived_from": "tosca.nodes.Compute",
                "requirements": [
                    {"network_link": {"capability": "tosca.capabilities.network.Linkable",
                                      "node": "tosca.nodes.network.Network",
                                      "occurrences": [1, 'UNBOUNDED']}},
                ],
            },
            "computeWithblocStorage": {
                "derived_from": "tosca.nodes.Compute",
                "requirements": [
                    {"bloc_attachement": {"capability": "tosca.capabilities.Attachment",
                                          "node": "tosca.nodes.Storage.BlockStorage",
                                          "occurrences": [1, 'UNBOUNDED']}},
                ],
            },
            "WebAppWithDatabase": {
                "derived_from": "WebApplication",
                "requirements": [
                    {"database_connection": {"capability": "tosca.capabilities.Endpoint.Database",
                                             "node": "Database",
                                             "occurrences": [1, 'UNBOUNDED']}},
                ],
            },
            "WebAppWithObjStorage": {
                "derived_from": "WebApplication",
                "requirements": [
                    {"object_connection": {"capability": "tosca.capabilities.Endpoint",
                                           "node": "tosca.nodes.Storage.ObjectStorage",
                                           "occurrences": [1, 'UNBOUNDED']}},
                ],
            },
            "WebAppWithObjBDD": {
                "derived_from": "WebApplication",
                "requirements": [
                    {"database_connection": {"capability": "tosca.capabilities.Endpoint.Database",
                                             "node": "Database",
                                             "occurrences": [1, 'UNBOUNDED']}},
                    {"object_connection": {"capability": "tosca.capabilities.Endpoint",
                                           "node": "tosca.nodes.Storage.ObjectStorage",
                                           "occurrences": [1, 'UNBOUNDED']}},
                ],
            },
            "StorageForContainer": {
                "derived_from": "tosca.nodes.Storage.ObjectStorage",
                "capabilities": {"storage": {"type": "tosca.capabilities.Storage"}},
            },
            "RuntimeForContainer": {
                "derived_from": "tosca.nodes.Container.Runtime",
                "capabilities": {"host": {"type": "tosca.capabilities.Compute"}},
            },
            "NetworkForContainer": {
                "derived_from": "tosca.nodes.network.Network",
                "capabilities": {"network": {"type": "tosca.capabilities.Network"}},
            },
            "ContainerWithDatabase": {
                "derived_from": "tosca.nodes.Container.Application",
                "requirements": [
                    {"database_connection": {"capability": "tosca.capabilities.Endpoint.Database",
                                             "node": "Database",
                                             "occurrences": [1, 'UNBOUNDED']}},
                ],
            },
        },

        # ---- Data types personnalises (utilises par les policies) ----
        "data_types": {
            "acme.datatypes.Location": {
                "derived_from": "tosca.datatypes.Root",
                "description": "A deployment location: region and/or availability zone.",
                "properties": {
                    "region":            {"type": "string", "required": False},
                    "availability_zone": {"type": "string", "required": False},
                },
            },
        },

        # ---- Policy types personnalises (non normatifs dans le coeur TOSCA) ----
        "policy_types": {
            "acme.policies.Placement": {
                "derived_from": "tosca.policies.Placement",
                "description": "Geographic placement constraint (region and/or availability zone).",
                "properties": {
                    "locations": {
                        "type": "list",
                        "required": True,
                        "entry_schema": {"type": "acme.datatypes.Location"},
                    },
                    "distribution": {
                        "type": "string",
                        "default": "multi_region",
                        "constraints": [{"valid_values": ["single_region", "multi_region"]}],
                    },
                },
            },
            "acme.policies.Availability": {
                "derived_from": "tosca.policies.Performance",
                "description": "Service-level availability target (percent).",
                "properties": {
                    "availability": {
                        "type": "float",
                        "required": True,
                        "constraints": [{"in_range": [0.0, 100.0]}],
                    },
                },
            },
            "acme.policies.Latency": {
                "derived_from": "tosca.policies.Performance",
                "description": "Maximum tolerated network latency.",
                "properties": {
                    "max_latency": {
                        "type": "scalar-unit.time",
                        "required": True,
                        "constraints": [{"greater_than": "0 ms"}],
                    },
                },
            },
            "acme.policies.Cost": {
                "derived_from": "tosca.policies.Root",
                "description": "Budget constraint over a billing period.",
                "properties": {
                    "max_cost": {"type": "float", "required": True},
                    "currency": {
                        "type": "string",
                        "default": "USD",
                        "constraints": [{"valid_values": ["USD", "EUR", "GBP"]}],
                    },
                    "period": {
                        "type": "string",
                        "default": "monthly",
                        "constraints": [{"valid_values": ["hourly", "daily", "monthly", "yearly"]}],
                    },
                },
            },
        },

        "topology_template": {"node_templates": {}},
    }

    # ---- Node templates ----
    for node in data.get("nodes", []):
        name = node.get("name")
        if not name:
            continue

        node_type = node.get("type", "")
        if node_type == "ObjectStorage":
            node_type = "tosca.nodes.Storage.ObjectStorage"
        elif node_type == "BlockStorage":
            node_type = "tosca.nodes.Storage.BlockStorage"

        node_def = {"type": node_type}

        props = {}
        for prop in node.get("properties", []) or []:
            if isinstance(prop, dict) and prop.get("value") not in (None, "null"):
                props[prop.get("name")] = prop.get("value")
        if props:
            node_def["properties"] = props

        caps = {}
        for cap in node.get("capabilities", []) or []:
            cap_name = cap.get("name")
            if not cap_name:
                continue
            cap_def = {}
            cap_props = {}
            for prop in cap.get("properties", []) or []:
                if isinstance(prop, dict) and prop.get("value") not in (None, "null"):
                    cap_props[prop.get("name")] = prop.get("value")
            if cap_props:
                cap_def["properties"] = cap_props
            caps[cap_name] = cap_def
        if caps:
            node_def["capabilities"] = caps

        reqs = []
        for req in node.get("requirements", []) or []:
            if isinstance(req, dict) and req.get("node"):
                reqs.append({req.get("name", "host"): req.get("node")})
        if reqs:
            node_def["requirements"] = reqs

        tosca["topology_template"]["node_templates"][name] = node_def

    # ---- Policies ----
    policies_list = []
    for policy in data.get("policies", []) or []:
        pname = policy.get("name")
        if not pname:
            continue
        ptype     = policy.get("type", "")
        full_type = POLICY_TYPE_MAP.get(ptype, ptype)
        policy_def = {"type": full_type}

        targets = [t for t in (policy.get("targets") or []) if t]
        if targets:
            policy_def["targets"] = targets

        pprops = {}
        for prop in policy.get("properties", []) or []:
            if isinstance(prop, dict) and prop.get("value") not in (None, "null"):
                pprops[prop.get("name")] = prop.get("value")
        if pprops:
            policy_def["properties"] = pprops

        policies_list.append({pname: policy_def})

    if policies_list:
        tosca["topology_template"]["policies"] = policies_list

    return tosca


def generate_tosca_yaml(json_output: dict) -> str:
    """Convertit le JSON en chaine TOSCA YAML."""
    tosca = convert_json_to_tosca(json_output)
    return yaml.dump(
        tosca,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )