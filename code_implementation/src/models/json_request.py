from pickle import TRUE
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum


class NodeType(str, Enum):
    Compute = "Compute"
    SoftwareComponent = "SoftwareComponent"
    WebServer = "WebServer"
    DBMS = "DBMS"
    Database = "Database"
    WebApplication = "WebApplication"
    Container_Application = "Container.Application"
    Network = "Network"
    LoadBalancer = "LoadBalancer"
    BlockStorage = "BlockStorage"
    ObjectStorage = "ObjectStorage"
    WebAppWithDatabase = "WebAppWithDatabase"
    WebAppWithObjStorage = "WebAppWithObjStorage"
    WebAppWithObjBDD = "WebAppWithObjBDD"
    computeWithnetwork = "computeWithnetwork"
    computeWithblocStorage = "computeWithblocStorage"
    computeWithblocNetwork = "computeWithblocNetwork"
    StorageForContainer = "StorageForContainer"
    RuntimeForContainer = "RuntimeForContainer"
    NetworkForContainer = "NetworkForContainer"
    ContainerWithDatabase = "ContainerWithDatabase"


class Property(BaseModel):
    name: str
    description: str
    type: str
    required: bool
    value: Any


class Capability(BaseModel):
    name: str = Field(description="each capability has a name that is specified according to the node type.")
    valid_source_types: List[str] = Field(description="each capability name has a valid Sources according to its name")
    properties: Optional[List[Property]] = Field(
        default_factory=list, description="each capability has a list of properties according to its name"
    )


class requirement(BaseModel):
    name: str = Field(description="each requirement has a name that is specified according to the node type.")
    node: str = Field(description="Each requirement has a relation with a node that has the capability that satisfies the requirement name.")


class Node(BaseModel):
    name: str = Field(description="A unique and descriptive name for the service")
    type: NodeType = Field(description="The most suitable type for the service")
    properties: Optional[List[Property]] = Field(default_factory=list, description="List of node properties")
    capabilities: Optional[List[Capability]] = Field(
        default_factory=list, description="List of capabilities associated with the node according to its type"
    )
    requirements: Optional[List[requirement]] = Field(
        default_factory=list, description="List of requirements associated with the node according to its type"
    )


class RelationType(str, Enum):
    DependsOn = "DependsOn"
    HostedOn = "HostedOn"
    ConnectsTo = "ConnectsTo"
    AttachesTo = "AttachesTo"
    RoutesTo = "RoutesTo"


class Relation(BaseModel):
    name: str = Field(description="A unique and descriptive name for the relationship")
    source: str = Field(description="The name of the source node")
    target: str = Field(description="The name of the target node")
    type: RelationType = Field(description="The most suitable type for the relationship between nodes")
    properties: Optional[List[Property]] = Field(default_factory=list, description="List of relation properties")


# ─────────────────────────────────────────────────────────────────────────────
# POLICIES (non-functional requirements)
# ─────────────────────────────────────────────────────────────────────────────

class PolicyType(str, Enum):
    Placement = "Placement"
    Availability = "Availability"
    Latency = "Latency"
    Cost = "Cost"


class Policy(BaseModel):
    name: str = Field(description="A unique and descriptive name for the policy")
    type: PolicyType = Field(description="The most suitable policy type")
    targets: List[str] = Field(
        default_factory=list,
        description="List of node names the policy applies to (must reference existing nodes)"
    )
    properties: Optional[List[Property]] = Field(
        default_factory=list,
        description="List of policy properties according to its type"
    )


class JsonRequest(BaseModel):
    description: str = Field(description="a brief description of the architecture")
    nodes: List[Node] = Field(description="List of services")
    policies: Optional[List[Policy]] = Field(
        default_factory=list,
        description="List of non-functional policies (placement, availability, latency, cost)"
    )


# ─────────────────────────────────────────────────────────────────────────────

def get_node_type_info() -> Dict[NodeType, Dict[str, str]]:
    return {
        NodeType.Compute: {
            "description": "represents one or more real or virtual processors of software applications or services along with other essential local resources. Collectively, the resources the compute node represents can logically be viewed as a (real or virtual) server. this type of node does not require network or bloc storage",
            "example": "virtual machine"
        },
        NodeType.computeWithnetwork: {
            "description": "represents a compute node that requires a network",
            "example": ""
        },
        NodeType.computeWithblocStorage: {
            "description": "represents a compute node that requires a bloc storage",
            "example": ""
        },
        NodeType.computeWithblocNetwork: {
            "description": "represents a compute node that requires a bloc storage and a network",
            "example": ""
        },
        NodeType.SoftwareComponent: {
            "description": "represents a generic software component that can be managed and run by a Compute Node Type.",
            "example": "firewall, elasticsearch, kibana"
        },
        NodeType.WebServer: {
            "description": "represents an abstract software component or service that is capable of hosting and providing management operations for one or more WebApplication nodes.",
            "example": "Tomcat, Apache, nodejs, Nginx"
        },
        NodeType.DBMS: {
            "description": "represents a typical relational, SQL Database Management System software component or service.",
            "example": "mongo DBMS, MySQL DBMS"
        },
        NodeType.Database: {
            "description": "represents a logical database that can be managed and hosted on a DBMS node.",
            "example": "MySQL BDD, Mongo BDD"
        },
        NodeType.WebApplication: {
            "description": "represents a software application that can be managed and run by a WebServer node and that does not require a database or object storage",
            "example": "java application, wordpress"
        },
        NodeType.WebAppWithDatabase: {
            "description": "represents a web application that requires a database",
            "example": ""
        },
        NodeType.WebAppWithObjStorage: {
            "description": "represents a web application that requires an object storage",
            "example": ""
        },
        NodeType.WebAppWithObjBDD: {
            "description": "represents a web application that requires an object storage and a database",
            "example": ""
        },
        NodeType.Container_Application: {
            "description": "represents an application that requires Container-level virtualization technology",
            "example": ""
        },
        NodeType.Network: {
            "description": "represents a simple, logical network service.",
            "example": ""
        },
        NodeType.LoadBalancer: {
            "description": "represents logical function that be used in conjunction with a Floating Address to distribute an application's traffic (load) across a number of instances of the application (e.g., for a clustered or scaled application).",
            "example": "Nginx LB"
        },
        NodeType.BlockStorage: {
            "description": "represents a server-local block storage device (i.e., not shared) offering evenly sized blocks of data from which raw storage volumes can be created.",
            "example": ""
        },
        NodeType.ObjectStorage: {
            "description": "represents storage that provides the ability to store data as objects (or BLOBs of data) without consideration for the underlying filesystem or devices.",
            "example": ""
        },
        NodeType.StorageForContainer: {
            "description": "represents an object storage related only to a container application",
            "example": ""
        },
        NodeType.RuntimeForContainer: {
            "description": "represents a runtime container node related only to a container application",
            "example": "docker engine"
        },
        NodeType.NetworkForContainer: {
            "description": "represents a network node related only to a container application",
            "example": ""
        },
        NodeType.ContainerWithDatabase: {
            "description": "represents a container application that requires a database",
            "example": ""
        },
    }


def get_relation_type_info() -> Dict[RelationType, Dict[str, str]]:
    return {
        RelationType.DependsOn: {
            "description": "This type represents a general dependency relationship between two nodes.",
            "example": "tomcat depends on java runtime",
        },
        RelationType.HostedOn: {
            "description": "This type represents a hosting relationship between two nodes.",
            "example": "Web Application HOSTED_ON Web Server, web server HOSTED_ON a virtual machine",
        },
        RelationType.ConnectsTo: {
            "description": "This type represents a network connection relationship between two nodes.",
            "example": "Web application CONNECTS_TO Database, frontend CONNECTS_TO backend",
        },
        RelationType.AttachesTo: {
            "description": "This type represents an attachment relationship between two nodes.",
            "example": "Block Storage ATTACHES_TO Compute Node",
        },
        RelationType.RoutesTo: {
            "description": "This type represents an intentional network routing between two Endpoints in different networks.",
            "example": "network 1 ROUTES_TO network 2, LOAD_BALANCER node ROUTES_TO a Web Application.",
        },
    }


def get_node_type_properties_info() -> Dict[str, Dict]:

    # --- Nœuds sans propriétés ---
    common_nodes_info = {
        "description": "this type of node has no properties",
        "properties": [],
    }
    nodes_types = [
        "Compute",
        "computeWithblocNetwork",
        "computeWithnetwork",
        "computeWithblocStorage",
        "Container.Application",
        "RuntimeForContainer",
        "ContainerWithDatabase",
    ]

    # --- Web Application ---
    common_web_app_info = {
        "description": "this type of node has one property.",
        "properties": [
            {
                "name": "context_root",
                "description": "The web application's context root which designates the application's URL path within the web server it is hosted on.",
                "type": "string",
                "required": False
            }
        ],
    }
    web_app_node_types = [
        "WebApplication",
        "WebAppWithDatabase",
        "WebAppWithObjStorage",
        "WebAppWithObjBDD",
    ]

    # --- Network ---
    common_network_info = {
        "description": "this type of node has one property",
        "properties": [
            {
                "name": "ip_version",
                "description": "The IP version of the requested network, valid_values: [4, 6] default: 4",
                "type": "integer",
                "required": False
            }
        ]
    }
    network_node_types = [
        "Network",
        "NetworkForContainer",
    ]

    # --- Object Storage ---
    common_object_storage_info = {
        "description": "this node type has three properties",
        "properties": [
            {"name": "name", "description": "The logical name (or ID) of the storage resource.", "type": "string", "required": True},
            {"name": "size", "description": "The requested initial storage size (default unit is in Gigabytes). it must be greater_or_equal: 0 MB", "type": "scalar-unit.size", "required": False},
            {"name": "maxsize", "description": "The requested maximum storage size (default unit is in Gigabytes). it must be greater_or_equal: 1 GB", "type": "scalar-unit.size", "required": False},
        ]
    }
    object_storage_node_types = [
        "ObjectStorage",
        "StorageForContainer",
    ]

    node_type_properties_info = {
        **{node: common_nodes_info.copy() for node in nodes_types},
        **{node: common_web_app_info.copy() for node in web_app_node_types},
        **{node: common_network_info.copy() for node in network_node_types},
        **{node: common_object_storage_info.copy() for node in object_storage_node_types},

        "SoftwareComponent": {
            "description": "this type of node has one property",
            "properties": [
                {
                    "name": "component_version",
                    "description": "The optional software component's version. It is mandatory for it to follow the format: major_version.minor_version.fix_version, for example: 3.1.0",
                    "type": "integer.integer.integer example 13.4.5",
                    "required": False
                },
            ],
        },
        "WebServer": {
            "description": "this type of node has no properties.",
            "properties": [],
        },
        "DBMS": {
            "description": "this type of node has two properties",
            "properties": [
                {"name": "root_password", "description": "The optional root password for the DBMS server.", "type": "string", "required": False},
                {"name": "port", "description": "The DBMS server's port.", "type": "integer", "required": False},
            ],
        },
        "Database": {
            "description": "this type of node has four properties",
            "properties": [
                {"name": "name", "description": "The logical database Name", "type": "string", "required": True},
                {"name": "port", "description": "The port the database service will use to listen for incoming data and requests.", "type": "integer", "required": False},
                {"name": "user", "description": "The special user account used for database administration.", "type": "string", "required": False},
                {"name": "password", "description": "The password associated with the user account provided in the 'user' property.", "type": "string", "required": False},
            ],
        },
        "LoadBalancer": {
            "description": "this type of node has one property.",
            "properties": [
                {"name": "algorithm", "description": "defines how traffic is distributed among multiple servers.", "type": "string", "required": False},
            ],
        },
        "BlockStorage": {
            "description": "this node type has four properties",
            "properties": [
                {"name": "name", "description": "The logical name (or ID) of the storage resource.", "type": "string", "required": True},
                {"name": "size", "description": "The requested storage size (default unit is MB). it must be greater_or_equal: 1 MB", "type": "scalar-unit.size", "required": False},
                {"name": "volume_id", "description": "ID of an existing volume (that is in the accessible scope of the requesting application)", "type": "string", "required": False},
                {"name": "snapshot_id", "description": "Some identifier that represents an existing snapshot that should be used when creating the block storage (volume).", "type": "string", "required": False},
            ],
        },
    }

    return node_type_properties_info


def get_relation_type_properties_info() -> Dict[str, List[Dict]]:
    return {
        "DependsOn": [],
        "HostedOn": [],
        "ConnectsTo": [
            {
                "name": "credential",
                "description": "The security credential to use to present to the target endpoint for authentication or authorization purposes.",
                "type": "credential",
                "required": False
            }
        ],
        "AttachesTo": [
            {
                "name": "location",
                "description": "The relative location (e.g., path on the file system), which provides the root location to address an attached node. Cannot be 'root', min_length: 1.",
                "type": "string",
                "required": True
            },
            {
                "name": "device",
                "description": "The logical device name for the attached device (represented by the target node). e.g., '/dev/hda1'",
                "type": "string",
                "required": False
            }
        ],
        "RoutesTo": [],
    }


def get_node_type_capabilities_info() -> Dict[str, Dict]:

    # --- Compute capabilities ---
    compute_capabilities = {
        "description": "This type of node has five capabilities",
        "capabilities": [
            {
                "name": "host",
                "valid_source_types": ["SoftwareComponent", "WebServer", "DBMS"],
                "properties": [
                    {"name": "name", "description": "The optional name (or identifier) of a specific compute resource for hosting.", "type": "string", "required": False},
                    {"name": "num_cpus", "description": "Number of (actual or virtual) CPUs associated with the Compute node. Must be >=1", "type": "integer", "required": False},
                    {"name": "cpu_frequency", "description": "Specifies the operating frequency of CPU's core. Expected frequency of one CPU.", "type": "scalar-unit.frequency", "required": False},
                    {"name": "disk_size", "description": "Size of the local disk available to applications (MB). Must be >=0", "type": "scalar-unit.size", "required": False},
                    {"name": "mem_size", "description": "Size of memory available to applications (MB). Must be >=0", "type": "scalar-unit.size", "required": False},
                ]
            },
            {
                "name": "os",
                "valid_source_types": [],
                "properties": [
                    {"name": "architecture", "description": "OS architecture. Examples: x86_32, x86_64", "type": "string", "required": False},
                    {"name": "type", "description": "OS type. Examples: linux, windows, mac", "type": "string", "required": False},
                    {"name": "distribution", "description": "OS distribution. Examples: debian, ubuntu", "type": "string", "required": False},
                    {"name": "version", "description": "OS version. Format: major.minor.fix, e.g., 3.1.0", "type": "integer.integer.integer example 3.1.0", "required": False},
                ]
            },
            {
                "name": "scalable",
                "valid_source_types": [],
                "properties": [
                    {"name": "min_instances", "description": "Minimum number of instances. Default=1", "type": "integer", "required": True},
                    {"name": "max_instances", "description": "Maximum number of instances. Default=1", "type": "integer", "required": True},
                    {"name": "default_instances", "description": "Optional default number of instances. Must be in range [min,max]", "type": "integer", "required": False},
                ]
            },
            {"name": "binding", "valid_source_types": [], "properties": []},
            {
                "name": "endpoint",
                "valid_source_types": [],
                "properties": [
                    {"name": "protocol", "description": "Protocol accepted. Examples: http, https, ftp, tcp, udp", "type": "string", "required": True},
                    {"name": "port", "description": "Optional port. 1-65535", "type": "PortDef", "required": False},
                    {"name": "secure", "description": "Whether endpoint is secure. Default: false", "type": "boolean", "required": False},
                    {"name": "url_path", "description": "Optional URL path", "type": "integer", "required": False},
                    {"name": "port_name", "description": "Optional network port name", "type": "string", "required": False},
                    {"name": "network_name", "description": "Optional network name", "type": "string", "required": False},
                    {"name": "initiator", "description": "Direction of connection: source/target/peer", "type": "string", "required": False},
                ]
            }
        ]
    }
    compute_node_types = [
        "Compute",
        "computeWithblocNetwork",
        "computeWithnetwork",
        "computeWithblocStorage",
    ]

    # --- Web Application capabilities ---
    common_web_app_capabilities = {
        "description": "This type of node has one capability",
        "capabilities": [
            {
                "name": "app_endpoint",
                "valid_source_types": [],
                "properties": [
                    {"name": "protocol", "description": "Protocol accepted. Examples: http, https, ftp, tcp, udp", "type": "string", "required": True},
                    {"name": "port", "description": "Optional port. 1-65535", "type": "PortDef", "required": False},
                    {"name": "secure", "description": "Whether endpoint is secure. Default: false", "type": "boolean", "required": False},
                    {"name": "url_path", "description": "Optional URL path", "type": "integer", "required": False},
                    {"name": "port_name", "description": "Optional network port name", "type": "string", "required": False},
                    {"name": "network_name", "description": "Optional network name", "type": "string", "required": False},
                    {"name": "initiator", "description": "Direction of connection: source/target/peer", "type": "string", "required": False},
                ]
            }
        ]
    }
    web_app_node_types = [
        "WebApplication",
        "WebAppWithDatabase",
        "WebAppWithObjStorage",
        "WebAppWithObjBDD",
    ]

    # --- Network capabilities ---
    common_network_capabilities = {
        "description": "This type of node has one capability",
        "capabilities": [
            {"name": "link", "valid_source_types": [], "properties": []}
        ]
    }
    network_node_types = [
        "Network",
        "NetworkForContainer",
    ]

    # --- Object Storage capabilities ---
    common_object_storage_capabilities = {
        "description": "This type of node has one capability",
        "capabilities": [
            {
                "name": "storage_endpoint",
                "valid_source_types": [],
                "properties": [
                    {"name": "protocol", "description": "Protocol accepted. Examples: http, https, ftp, tcp, udp", "type": "string", "required": True},
                    {"name": "port", "description": "Optional port. 1-65535", "type": "PortDef", "required": False},
                    {"name": "secure", "description": "Whether endpoint is secure. Default: false", "type": "boolean", "required": False},
                    {"name": "url_path", "description": "Optional URL path", "type": "integer", "required": False},
                    {"name": "port_name", "description": "Optional network port name", "type": "string", "required": False},
                    {"name": "network_name", "description": "Optional network name", "type": "string", "required": False},
                    {"name": "initiator", "description": "Direction of connection: source/target/peer", "type": "string", "required": False},
                ]
            }
        ]
    }
    object_storage_node_types = [
        "ObjectStorage",
        "StorageForContainer",
    ]

    # --- Empty capabilities ---
    empty_capabilities = {"description": "This type of node has no capabilities", "capabilities": []}
    empty_capabilities_node_types = [
        "Container.Application",
        "ContainerWithDatabase",
    ]

    # --- RuntimeForContainer capabilities ---
    runtime_for_container_capabilities = {
        "description": "This type of node has one capability",
        "capabilities": [
            {
                "name": "host",
                "valid_source_types": ["Container.Application", "ContainerWithDatabase"],
                "properties": []
            }
        ]
    }

    # --- DBMS capabilities ---
    dbms_capabilities = {
        "description": "This type of node has one capability",
        "capabilities": [
            {
                "name": "host",
                "valid_source_types": ["Database"],
                "properties": [
                    {"name": "name", "description": "The optional name (or identifier) of a specific compute resource for hosting.", "type": "string", "required": False},
                    {"name": "num_cpus", "description": "Number of CPUs associated with the Compute node.", "type": "integer", "required": False},
                    {"name": "cpu_frequency", "description": "CPU frequency", "type": "scalar-unit.frequency", "required": False},
                    {"name": "disk_size", "description": "Disk size (MB)", "type": "scalar-unit.size", "required": False},
                    {"name": "mem_size", "description": "Memory size (MB)", "type": "scalar-unit.size", "required": False},
                ]
            }
        ]
    }

    # --- LoadBalancer capabilities ---
    load_balancer_capabilities = {
        "description": "This type of node has one capability",
        "capabilities": [
            {
                "name": "client",
                "valid_source_types": [],
                "properties": [
                    {"name": "protocol", "description": "Protocol name", "type": "string", "required": True},
                    {"name": "port", "description": "Port 1-65535", "type": "PortDef", "required": False},
                    {"name": "secure", "description": "Whether secure. Default: false", "type": "boolean", "required": False},
                    {"name": "url_path", "description": "Optional URL path", "type": "integer", "required": False},
                    {"name": "port_name", "description": "Optional port name", "type": "string", "required": False},
                    {"name": "network_name", "description": "Optional network name", "type": "string", "required": False},
                    {"name": "initiator", "description": "Connection direction", "type": "string", "required": False},
                    {"name": "floating", "description": "Floating IP allocation", "type": "boolean", "required": False},
                    {"name": "dns_name", "description": "Optional DNS name", "type": "string", "required": False},
                ]
            }
        ]
    }

    # --- BlockStorage capabilities ---
    block_storage_capabilities = {
        "description": "This type of node has one capability",
        "capabilities": [{"name": "attachment", "valid_source_types": [], "properties": []}]
    }

    # --- Dictionnaire final ---
    node_type_capabilities_info = {
        **{node: compute_capabilities.copy() for node in compute_node_types},
        **{node: common_web_app_capabilities.copy() for node in web_app_node_types},
        **{node: common_network_capabilities.copy() for node in network_node_types},
        **{node: common_object_storage_capabilities.copy() for node in object_storage_node_types},
        **{node: empty_capabilities.copy() for node in empty_capabilities_node_types},
        "RuntimeForContainer": runtime_for_container_capabilities,
        "DBMS": dbms_capabilities,
        "LoadBalancer": load_balancer_capabilities,
        "BlockStorage": block_storage_capabilities,
    }

    return node_type_capabilities_info


# ─────────────────────────────────────────────────────────────────────────────
# POLICY CATALOGS (same pattern as node type catalogs)
# ─────────────────────────────────────────────────────────────────────────────

def get_policy_type_info() -> Dict[PolicyType, Dict[str, str]]:
    return {
        PolicyType.Placement: {
            "description": "governs the geographic placement of nodes. Use it when the request specifies regions, availability zones, or where the application must be deployed.",
            "example": "deployed across UK, USA and Europe",
        },
        PolicyType.Availability: {
            "description": "specifies a service-level availability target in percent. Use it when the request mentions an availability or uptime requirement.",
            "example": "99.999% availability",
        },
        PolicyType.Latency: {
            "description": "specifies the maximum tolerated network latency. Use it when the request mentions a latency or response-time requirement.",
            "example": "1ms latency",
        },
        PolicyType.Cost: {
            "description": "specifies a budget constraint over a billing period. Use it when the request mentions a cost or budget.",
            "example": "a cost of $100 per month",
        },
    }


def get_policy_type_properties_info() -> Dict[str, Dict]:
    return {
        "Placement": {
            "description": "this policy has one required property",
            "properties": [
                {"name": "locations", "description": "A LIST of location objects. Each object may contain a 'region' (string) and/or an 'availability_zone' (string). The user may specify a region, an availability zone, or both.", "type": "list of {region, availability_zone}", "required": True},
            ],
        },
        "Availability": {
            "description": "this policy has one required property",
            "properties": [
                {"name": "availability", "description": "Target availability in percent, e.g. 99.999. Must be in range [0.0, 100.0].", "type": "float", "required": True},
            ],
        },
        "Latency": {
            "description": "this policy has one required property",
            "properties": [
                {"name": "max_latency", "description": "Maximum tolerated latency WITH a time unit, e.g. '1 ms', '50 ms'. Must be > 0.", "type": "scalar-unit.time", "required": True},
            ],
        },
        "Cost": {
            "description": "this policy has three properties",
            "properties": [
                {"name": "max_cost", "description": "The maximum cost as a number, e.g. 100.0", "type": "float", "required": True},
                {"name": "currency", "description": "Currency: one of USD, EUR, GBP. Default USD.", "type": "string", "required": False},
                {"name": "period", "description": "Billing period: one of hourly, daily, monthly, yearly. Default monthly.", "type": "string", "required": False},
            ],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Vérification d'alignement (à lancer une fois au démarrage)
# ─────────────────────────────────────────────────────────────────────────────

def check_alignment():
    props = get_node_type_properties_info()
    caps  = get_node_type_capabilities_info()
    valid = {nt.value for nt in NodeType}

    ok = True
    for key in props:
        if key not in valid:
            print(f"⚠️  PROPS clé inconnue : '{key}'  (pas dans NodeType)")
            ok = False
    for key in caps:
        if key not in valid:
            print(f"⚠️  CAPS  clé inconnue : '{key}'  (pas dans NodeType)")
            ok = False

    # Alignement des catalogues de policies avec PolicyType
    policy_info  = get_policy_type_info()
    policy_props = get_policy_type_properties_info()
    valid_pol = {pt.value for pt in PolicyType}
    for key in policy_props:
        if key not in valid_pol:
            print(f"⚠️  POLICY PROPS clé inconnue : '{key}'  (pas dans PolicyType)")
            ok = False
    for pt in PolicyType:
        if pt not in policy_info:
            print(f"⚠️  POLICY INFO manquant pour : '{pt.value}'")
            ok = False

    if ok:
        print("✅ Toutes les clés sont alignées avec NodeType / PolicyType.")