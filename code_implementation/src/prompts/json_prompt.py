from models.json_request import RelationType

from models.json_request import (
    NodeType, get_node_type_info, get_relation_type_info,
    get_node_type_properties_info, get_relation_type_properties_info,
    get_node_type_capabilities_info,
    PolicyType, get_policy_type_info, get_policy_type_properties_info,
)

NODE_TYPE_INFO = get_node_type_info()

node_types_formatted = "\n".join(
    f'{i+1}. "{nt.value}" : {NODE_TYPE_INFO[nt]["description"]} '
    f'(ex: {NODE_TYPE_INFO[nt]["example"]})'
    for i, nt in enumerate(NodeType)
)

RELATION_TYPE_INFO =  get_relation_type_info()

relation_types_formatted = "\n".join(
    f'{i+1}. "{nt.value}" : {RELATION_TYPE_INFO[nt]["description"]} '
    f'(ex: {RELATION_TYPE_INFO[nt]["example"]})'
    for i, nt in enumerate(RelationType)
)

NODE_TYPE_PROPERTIES_INFO = get_node_type_properties_info()

prop_types_formatted = "\n".join(
    f'{i+1}. "{nt}" : {NODE_TYPE_PROPERTIES_INFO[nt]["description"]} '
    f'(properties: {", ".join(f"{p["name"]} ({p["type"]}, {"required" if p["required"] else "optionnel"})" for p in NODE_TYPE_PROPERTIES_INFO[nt]["properties"])})'
    for i, nt in enumerate(NODE_TYPE_PROPERTIES_INFO)
)

RELATION_TYPE_PROPERTIES_INFO = get_relation_type_properties_info()

rel_types_formatted = "\n".join(
    f'{i+1}. "{rt}" : '
    f'(properties: {", ".join(f"{p["name"]} ({p["type"]}, {"required" if p["required"] else "optionnel"})" for p in RELATION_TYPE_PROPERTIES_INFO[rt])})'
    if RELATION_TYPE_PROPERTIES_INFO[rt]
    else f'{i+1}. "{rt}" : (properties: aucune)'
    for i, rt in enumerate(RELATION_TYPE_PROPERTIES_INFO)
)

NODE_TYPE_CAPABILITIES_INFO = get_node_type_capabilities_info()

capabilities_types_formatted = []

for i, (node_type, node_info) in enumerate(NODE_TYPE_CAPABILITIES_INFO.items(), start=1):
    capabilities = node_info.get("capabilities", [])

    if not capabilities:
        capabilities_types_formatted.append(f'{i}. "{node_type}": (capabilities: none)')
        continue

    caps_formatted = []
    for cap in capabilities:
        properties = cap.get("properties", [])
        if properties:
            props_formatted = ", ".join(
                f'{p["name"]} ({p["type"]}, {"required" if p.get("required") else "optional"})'
                for p in properties
            )
        else:
            props_formatted = "none"

        valid_sources = cap.get("valid_source_types", [])
        caps_formatted.append(
            f'{cap["name"]} (valid_source_types: {valid_sources}, properties: {props_formatted})'
        )

    capabilities_types_formatted.append(f'{i}. "{node_type}": ' + "; ".join(caps_formatted))

# Chaîne finale
formatted_output = "\n".join(capabilities_types_formatted)


# ─────────────────────────────────────────────────────────────────────────────
# POLICIES — formatage (même pattern que les nodes)
# ─────────────────────────────────────────────────────────────────────────────

POLICY_TYPE_INFO = get_policy_type_info()
policy_types_formatted = "\n".join(
    f'{i+1}. "{pt.value}" : {POLICY_TYPE_INFO[pt]["description"]} (ex: {POLICY_TYPE_INFO[pt]["example"]})'
    for i, pt in enumerate(PolicyType)
)

POLICY_TYPE_PROPERTIES_INFO = get_policy_type_properties_info()
policy_props_formatted = "\n".join(
    f'{i+1}. "{pt}" : {POLICY_TYPE_PROPERTIES_INFO[pt]["description"]} '
    f'(properties: {", ".join(f"{p["name"]} ({p["type"]}, {"required" if p["required"] else "optionnel"})" for p in POLICY_TYPE_PROPERTIES_INFO[pt]["properties"])})'
    for i, pt in enumerate(POLICY_TYPE_PROPERTIES_INFO)
)


json_request_prompt = f"""
ROLE:
You are expert on application architecture modeling.

CONTEXT:
You will receive a user request in natural language between
<request> and </request> tags.

INSTRUCTIONS:

1. Analyze the request carefully.
2. Extract from the request the components of the architecture, e.g., web application, MySQL, etc.
3. For each component, Provide a unique name reflecting the name of the component service, e.g., web_application, MySQL_BDD, etc.
4. For each component, assign a type. You MUST follow these rules in order:

        - A Docker Engine, Docker runtime, or any container runtime engine MUST always be typed as 'RuntimeForContainer'. NEVER type it as 'SoftwareComponent' or 'Compute'.
        - If the architecture contains a node of type database and a node of type web application and there is no object storage node in the architecture, Then the web application will not have the type WebApplication, change it to 'WebAppWithDatabase'.
        - If the architecture contains a node of type object storage and a node of type web application and there is no database node in the architecture, Then the web application will not have the type WebApplication, change it to 'WebAppWithObjStorage'.
        - If the architecture contains a node of type object storage and a node of type web application and also a node of type database, Then the web application will not have the type WebApplication, change it to 'WebAppWithObjBDD'.
        - If the architecture contains a node of type network and a node of type compute and there is no bloc storage node, Then change the type of the compute node to 'computeWithNetwork'.
        - If the architecture contains a node of type bloc storage and a node of type compute and there is no network node, Then change the type of the compute node to 'computeWithblocStorage'.
        - If the architecture contains a node of type bloc storage and a node of type compute and also a node of type network, Then change the type of the compute node to 'computeWithblocNetwork'.
        - If the architecture contains a node of type container application and an object storage node, Then change the type of the object storage node to 'StorageForContainer'.
        - If the architecture contains a node of type container application and a network node, Then change the type of the network node to 'NetworkForContainer'.

        You must follow the allowed values: {node_types_formatted}

5. For each component, if properties are specified in the request, you must include them according to its type. Also, if a component has required properties, even if they are not present in the request, you must add them by providing appropriate values. Information about each component type's properties can be found in the following list that you must respect: {prop_types_formatted}

6. For each component, if capabilities are specified in the request, you must include them according to its type. Also, if a component has required capability values, even if they are not present in the request, you must add them by providing appropriate values. The information on the capabilities of each type is in the following list, which you must respect: {formatted_output}. If a type of node does not have associated capabilities, do not invent them; just set capabilities to an empty list [].

7. For each component, provide the list of its requirements following these rules:

        - A node of type SoftwareComponent, WebServer, RuntimeForContainer or DBMS has a requirement named 'host' on a Compute node if a compute node exists.
        - A node of type WebApplication has a requirement named 'host' on a WebServer node, if a WebServer node exists.
        - A node of type Database has a requirement named 'host' on a DBMS node, if a DBMS node exists.
        - A node of type LoadBalancer may have a requirement named 'application' on a web application node if a node of type web application exists in the architecture, else there is no requirement for this node.
        - A node of type WebApplication may have a requirement named 'dependency' on a SoftwareComponent node if a SoftwareComponent node exists in the architecture, else there is no requirement for this node.
        - A node of type 'Container.Application' MUST have ALL THREE of these requirements: 'storage' related to the node of type 'StorageForContainer', 'network' related to the node of type 'NetworkForContainer', 'host' related to the node of type 'RuntimeForContainer'.
        - A node of type 'ContainerWithDatabase' MUST have ALL FOUR of these requirements: 'host' related to the 'RuntimeForContainer' node, 'database_connection' related to the database node, 'storage' related to a 'StorageForContainer' node, 'network' related to a 'NetworkForContainer' node.
        - A node of type 'WebAppWithDatabase' has as requirements 'database_connection' related to the database node.
        - A node of type 'WebAppWithObjStorage' has 'object_connection' related to the object storage node.
        - A node of type 'WebAppWithObjBDD' has as requirements 'object_connection' related to the object storage node and 'database_connection' related to the database node.
        - A node of type 'computeWithNetwork' has as requirements 'network_link' related to the network node.
        - A node of type 'computeWithblocStorage' has as requirements 'bloc_attachement' related to the bloc storage node.
        - A node of type 'computeWithblocNetwork' has as requirements 'bloc_attachement' related to the bloc storage node and 'network_link' related to the network node.

8. Non-functional requirements -> policies. If the request expresses a placement constraint
   (regions / availability zones / "deployed across ..."), an availability/uptime target,
   a latency requirement, or a cost/budget, you MUST add a corresponding policy.
   For each policy provide:
       - a unique 'name' (e.g. "placement_policy", "availability_policy")
       - a 'type' taken STRICTLY from the allowed policy list below
       - 'targets': the list of node names the policy applies to (must reference existing nodes)
       - 'properties': the policy properties according to its type (same {{name, value, type, required, description}} shape as node properties)

   Allowed policy types: {policy_types_formatted}

   Policy properties you MUST respect: {policy_props_formatted}

   ──────────────────────────────────────────────────────────────────────────
   CRITICAL RULE - ONE POLICY PER DISTINCT VALUE (applies to EVERY policy type):
   A single policy may group several nodes in its 'targets' ONLY when those nodes share
   the EXACT SAME value. If nodes have DIFFERENT values, you MUST emit a SEPARATE policy
   for each distinct value, each with its own 'targets'. NEVER merge nodes that have
   different values into one policy.
       - Same value shared by N nodes  -> ONE policy, targets = those N nodes.
       - K different values across nodes -> K separate policies, one per value.

   SPECIAL CASE - Placement:
   A placement policy says WHERE its targets are deployed. The 'locations' list expresses the
   set of locations allowed FOR THOSE TARGETS — it is NOT a way to list several nodes each
   pinned to a different place.
       - Two (or more) nodes deployed in the SAME location -> ONE placement policy targeting all
         of them, with that single location in 'locations'.
       - Two (or more) nodes deployed in DIFFERENT locations -> as many SEPARATE placement
         policies as there are distinct locations, each targeting only the node(s) at that
         location, each with its own single-location 'locations' list. NEVER put two different
         fixed locations in the same 'locations' list together with several targets: that makes
         it impossible to know which location applies to which node, and is FORBIDDEN.
       - A 'locations' list with MULTIPLE entries is reserved for ONE target (or a group of
         targets sharing the SAME set of allowed locations) that MAY be placed in any of several
         locations (multi-region deployment). It is never used to encode several nodes at
         different fixed places.

   Example A — VM_a is in eu-west-1a and VM_b is in eu-east-1a (DIFFERENT locations).
   You MUST produce TWO placement policies:
       [
         {{"name": "placement_vm_a", "type": "Placement", "targets": ["VM_a"],
           "properties": [{{"name": "locations",
                            "value": [{{"region": "eu-west-1", "availability_zone": "eu-west-1a"}}],
                            "type": "list", "required": true, "description": ""}}]}},
         {{"name": "placement_vm_b", "type": "Placement", "targets": ["VM_b"],
           "properties": [{{"name": "locations",
                            "value": [{{"region": "eu-east-1", "availability_zone": "eu-east-1a"}}],
                            "type": "list", "required": true, "description": ""}}]}}
       ]

   Example B — VM_a and VM_b are BOTH in eu-west-1 (SAME location).
   You produce ONE placement policy:
       [
         {{"name": "placement_policy", "type": "Placement", "targets": ["VM_a", "VM_b"],
           "properties": [{{"name": "locations",
                            "value": [{{"region": "eu-west-1"}}],
                            "type": "list", "required": true, "description": ""}}]}}
       ]

   Example C — a single VM that may be placed in UK or USA or Europe (multi-region, ONE target).
   You produce ONE placement policy with several entries in 'locations':
       [
         {{"name": "placement_policy", "type": "Placement", "targets": ["VM_a"],
           "properties": [{{"name": "locations",
                            "value": [{{"region": "UK"}}, {{"region": "USA"}}, {{"region": "Europe"}}],
                            "type": "list", "required": true, "description": ""}}]}}
       ]

   If the request expresses NO non-functional requirement, set "policies" to an empty list [].

9. Output a valid JSON including nodes information, policies and a brief description of the architecture.

Constraints:
    - Do not add components that are not mentioned in the request.
    - Every component mentioned in the request must be present in the final response.
    - Node types must come from the allowed list; do not invent new types.
    - Node properties must come STRICTLY from the allowed list. Do NOT add properties that are not defined for a given type (e.g., DBMS only accepts 'root_password' and 'port', NEVER 'component_version' or any other invented property).
    - Node capabilities must come from the allowed list; do not invent new capabilities.
    - Policy types and policy properties must come STRICTLY from the allowed policy list; do not invent new ones.
    - A policy's 'targets' must reference existing node names. Never leave targets empty.
    - A policy must NEVER group nodes that have different values. In particular, a placement
      policy must never group nodes that are in different locations: create one separate
      placement policy per distinct location.
    - If a component does not exactly match an allowed type, select the closest semantic match from the approved list.
    - A Docker Engine or any container runtime MUST be typed as 'RuntimeForContainer', never as 'SoftwareComponent'.
    - Compute nodes have always no properties.
    - Every requirement's 'node' field MUST reference an existing node name in the architecture. NEVER set 'node' to null or an empty string.
A version must follow the format a.b.c, where a, b, and c are digits.

Load balancer traffic must always be routed to the application layer and not to compute resources.
GOAL:
Extract, complete, and structure a natural language request into a structured JSON format.
"""