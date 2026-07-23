#!/usr/bin/env python3
"""
tosca_candidate_matcher.py
==========================
Input  : a TOSCA template (YAML).
Output : a JSON listing, for every "matchable" node
         (compute, network, database, loadbalancer, object_storage, block_storage),
         the CANDIDATE OFFERS with ALL their column values.

Built to replay several templates:
    python tosca_candidate_matcher.py TEMPLATE.yaml \
        --registries ./registries --out result.json

Matching = multi-criteria filter (region, SLA, budget, technical requirements),
then sorted by price. Latency is NOT an offer-level criterion (inter-region property).
"""
from __future__ import annotations
import argparse, json, math, re, sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


# =====================================================================
# 1. NORMALIZED REGISTRY MODEL
# =====================================================================
@dataclass
class Offer:
    offer_id: str
    provider: str
    service_type: str
    region: str
    sla_single: Optional[float]
    sla_multi: Optional[float]
    price_month: Optional[float]
    specs: dict = field(default_factory=dict)   # normalized technical requirements
    columns: dict = field(default_factory=dict) # full row (EN columns, JSON-safe)


class Catalog:
    def __init__(self):
        self.by_type: dict[str, list[Offer]] = defaultdict(list)

    def add(self, o: Offer):
        self.by_type[o.service_type].append(o)

    def summary(self) -> dict:
        return {k: len(v) for k, v in self.by_type.items()}


# ---------- parsing helpers ----------
def _f(x):
    if x is None:
        return None
    if isinstance(x, str):
        x = x.strip()
        if x in ("", "—", "-", "n/a", "null", "nan"):
            return None
        x = x.replace(",", ".")
    try:
        v = float(x)
        return None if math.isnan(v) else round(v, 4)
    except (ValueError, TypeError):
        return None


def _split(x):
    if not isinstance(x, str):
        return []
    return [p.strip() for p in x.replace(",", ";").split(";") if p.strip()]


# ---------- normalisation of exact comparisons ----------
# Known synonyms: different spellings of the same value.
_SYNONYMS = {
    # architectures
    "amd64": "x86_64", "x64": "x86_64", "x8664": "x86_64", "x86": "x86_64",
    "aarch64": "arm64", "arm": "arm64",
    # ip
    "ipv4": "ipv4", "ip4": "ipv4", "4": "ipv4",
    "ipv6": "ipv6", "ip6": "ipv6", "6": "ipv6",
    # network layers
    "layer7": "l7", "7": "l7", "layer4": "l4", "4layer": "l4",
}


def _norm(s):
    """Normalise a value for a robust comparison:
    lowercase, strip spaces/hyphens/underscores, then apply synonyms.
    E.g. 'x86_64' and 'AMD64' -> 'x86_64' ; 'round-robin' == 'round_robin'."""
    if s is None:
        return None
    t = re.sub(r"[\s_\-]+", "", str(s).strip().lower())
    if t == "":
        return None
    return _SYNONYMS.get(t, t)


def _norm_set(values):
    """Normalise a list/set of values into a set (without None)."""
    if values is None:
        return set()
    if not isinstance(values, (list, set, tuple)):
        values = [values]
    return {n for n in (_norm(v) for v in values) if n is not None}


def _clean_cell(v):
    """Make a value JSON-safe (NaN->None, numpy->python, SLA rounded)."""
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 4)
    if v is None:
        return None
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return None if math.isnan(float(v)) else round(float(v), 4)
    except Exception:
        pass
    if isinstance(v, str) and v.strip() == "—":
        return None
    return v


# ---------- loader (EN registries) ----------
REGISTRY_FILES = {
    "compute":        "offres_compute_en.xlsx",
    "block_storage":  "offres_block_storage_en.xlsx",
    "object_storage": "offres_object_storage_en.xlsx",
    "loadbalancer":   "offres_loadbalancer_en.xlsx",
    "database":       "offres_database_en.xlsx",
    "network":        "offres_network_en.xlsx",
}


def load_catalog(folder: str) -> Catalog:
    cat = Catalog()
    for service_type, fname in REGISTRY_FILES.items():
        df = pd.read_excel(f"{folder}/{fname}")
        for raw in df.to_dict("records"):
            cols = {k: _clean_cell(v) for k, v in raw.items()}
            if service_type == "network":
                sla_single = sla_multi = _f(raw.get("sla"))
            else:
                sla_single = _f(raw.get("sla_single_zone"))
                sla_multi  = _f(raw.get("sla_multi_zone"))

            if service_type == "compute":
                specs = {"cpu": _f(raw.get("cpu")), "memory_gb": _f(raw.get("memory_gb")),
                         "disk_gb": _f(raw.get("disk_gb")),
                         "architecture": str(raw.get("architecture", "")).strip(),
                         "os_type": _split(raw.get("os_type")),
                         "os_distribution": _split(raw.get("os_distribution"))}
            elif service_type == "database":
                specs = {"engine": str(raw.get("engine", "")).strip().lower(),
                         "versions": [str(v) for v in _split(raw.get("supported_versions"))]}
            elif service_type == "network":
                specs = {"layer": str(raw.get("layer", "")).strip(),
                         "ip_version": _split(raw.get("ip_version"))}
            elif service_type == "loadbalancer":
                specs = {"lb_type": str(raw.get("lb_type", "")).strip(),
                         "scope": str(raw.get("scope", "")).strip()}
            elif service_type == "block_storage":
                specs = {"capacity_gb": _f(raw.get("capacity_gb"))}
            else:  # object_storage
                specs = {"price_gb": _f(raw.get("price_gb"))}

            cat.add(Offer(offer_id=str(raw.get("offer_id")), provider=str(raw.get("provider")).strip(),
                          service_type=service_type, region=str(raw.get("region")).strip(),
                          sla_single=sla_single, sla_multi=sla_multi,
                          price_month=_f(raw.get("price_month")), specs=specs, columns=cols))
    return cat


# =====================================================================
# 2. TAXONOMY  logical region -> concrete region codes
# =====================================================================
TAXONOMY = {
    "usa": {"us-east-1", "us-east-2", "us-west-2", "us-central1", "us-east1", "us-west1", "eastus", "westus2"},
    "europe": {"eu-central-1", "eu-west-1", "eu-west-2", "eu-west-3", "europe-west1", "europe-west2",
               "europe-west3", "europe-west4", "europe-west9", "northeurope", "westeurope", "uksouth", "francecentral"},
    "uk": {"eu-west-2", "europe-west2", "uksouth"},
    "france": {"eu-west-3", "europe-west9", "francecentral"},
    "germany": {"eu-central-1", "europe-west3"},
    "ireland": {"eu-west-1", "northeurope"},
    "netherlands": {"europe-west4", "westeurope"},
    "belgium": {"europe-west1"},
    "brazil": {"sa-east-1"}, "south_america": {"sa-east-1"},
    "global": {"global"},
}
_ALIAS = {"usa": "usa", "us": "usa", "united states": "usa", "etats-unis": "usa",
          "europe": "europe", "eu": "europe", "uk": "uk", "royaume-uni": "uk",
          "france": "france", "allemagne": "germany", "germany": "germany",
          "irlande": "ireland", "ireland": "ireland", "pays-bas": "netherlands",
          "netherlands": "netherlands", "belgique": "belgium", "belgium": "belgium",
          "bresil": "brazil", "brazil": "brazil", "global": "global"}

# Region -> known AZs (to validate and pin an AZ). Also a fallback if
# region_taxonomy.xlsx ('az' column) is absent.
REGION_AZ = {
    "us-east-1": {"us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d", "us-east-1e", "us-east-1f"},
    "us-east-2": {"us-east-2a", "us-east-2b", "us-east-2c"},
    "us-west-2": {"us-west-2a", "us-west-2b", "us-west-2c", "us-west-2d"},
    "eu-central-1": {"eu-central-1a", "eu-central-1b", "eu-central-1c"},
    "eu-west-1": {"eu-west-1a", "eu-west-1b", "eu-west-1c"},
    "eu-west-2": {"eu-west-2a", "eu-west-2b", "eu-west-2c"},
    "eu-west-3": {"eu-west-3a", "eu-west-3b", "eu-west-3c"},
    "sa-east-1": {"sa-east-1a", "sa-east-1b", "sa-east-1c"},
    "europe-west1": {"europe-west1-b", "europe-west1-c", "europe-west1-d"},
    "europe-west2": {"europe-west2-a", "europe-west2-b", "europe-west2-c"},
    "europe-west3": {"europe-west3-a", "europe-west3-b", "europe-west3-c"},
    "europe-west4": {"europe-west4-a", "europe-west4-b", "europe-west4-c"},
    "europe-west9": {"europe-west9-a", "europe-west9-b", "europe-west9-c"},
    "us-central1": {"us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f"},
    "us-east1": {"us-east1-b", "us-east1-c", "us-east1-d"},
    "us-west1": {"us-west1-a", "us-west1-b", "us-west1-c"},
    "northeurope": {"1", "2", "3"}, "westeurope": {"1", "2", "3"}, "uksouth": {"1", "2", "3"},
    "francecentral": {"1", "2", "3"}, "eastus": {"1", "2", "3"}, "westus2": {"1", "2", "3"},
    "global": set(),
}


def load_taxonomy(folder: str, filename: str = "region_taxonomy.xlsx") -> bool:
    """
    If <folder>/region_taxonomy.xlsx exists, (re)build TAXONOMY and REGION_AZ from the
    'taxonomie' sheet (columns logical_region, region_code, az). Otherwise keep the
    embedded tables. Returns True if loaded from file.
    """
    import os
    path = os.path.join(folder, filename)
    if not os.path.exists(path):
        return False
    df = pd.read_excel(path, sheet_name="taxonomie")
    built: dict[str, set[str]] = defaultdict(set)
    az_built: dict[str, set[str]] = defaultdict(set)
    for r in df.to_dict("records"):
        lr = str(r.get("logical_region", "")).strip().lower()
        code = str(r.get("region_code", "")).strip()
        if lr and code:
            built[lr].add(code)
        az_cell = r.get("az")
        if code and isinstance(az_cell, str) and az_cell.strip() not in ("", "—"):
            for a in az_cell.replace(",", ";").split(";"):
                if a.strip():
                    az_built[code].add(a.strip())
    if built:
        TAXONOMY.clear()
        TAXONOMY.update(built)
    if az_built:
        REGION_AZ.update(az_built)
    return True


def _az_to_region(az: str) -> Optional[str]:
    """us-east-1a -> us-east-1 ; europe-west9-b -> europe-west9 ;
       Azure numeric AZ ('1','2','3') -> None (region must come from the region field)."""
    az = az.strip()
    if not az or az.isdigit():
        return None
    if "-" in az and az[-1].isalpha():
        return az[:-1] if az[-2].isdigit() else az.rsplit("-", 1)[0]
    return None


def resolve_placement(locations: list, distribution: str = "multi_region") -> dict:
    """
    Resolve locations into: concrete regions, target AZs, AZs per region,
    zone scope (single/multi) and warnings.
    RULE: if an AZ is given, it WINS -> pin the AZ's region
    (do not expand through a logical region).
    """
    regions: set = set()
    azs: set = set()
    az_by_region: dict = defaultdict(set)
    warnings: list = []

    for loc in locations or []:
        if not isinstance(loc, dict):
            continue
        az = (loc.get("availability_zone") or "").strip()
        reg = (loc.get("region") or "").strip()

        if az:  # ---- an AZ is specified: it takes precedence ----
            r = _az_to_region(az)
            if r is None and reg:  # Azure numeric AZ -> region from the region field
                key = _ALIAS.get(reg.lower(), reg.lower())
                codes = TAXONOMY.get(key, {reg})
                if len(codes) == 1:
                    r = next(iter(codes))
                else:
                    warnings.append(f"AZ '{az}' with ambiguous region '{reg}': region undetermined")
            if r is None:
                warnings.append(f"AZ '{az}' without a determinable region: ignored")
                continue
            # consistency with the region field if given and concrete
            if reg:
                key = _ALIAS.get(reg.lower(), reg.lower())
                codes = TAXONOMY.get(key, {reg})
                if r not in codes:
                    warnings.append(f"AZ '{az}' does not belong to '{reg}': keeping the AZ ({r})")
            # validate the AZ exists
            known = REGION_AZ.get(r)
            if known and az not in known:
                warnings.append(f"AZ '{az}' unknown for '{r}' (known: {sorted(known)})")
            regions.add(r)
            azs.add(az)
            az_by_region[r].add(az)
        elif reg:  # ---- region only: logical expansion -> codes ----
            key = _ALIAS.get(reg.lower(), reg.lower())
            regions |= TAXONOMY.get(key, {reg})

    # zone scope: a single AZ -> single-zone ; otherwise based on distribution
    if azs:
        zone_scope = "single_zone" if len(azs) == 1 else "multi_zone"
    else:
        zone_scope = "multi_zone" if distribution == "multi_region" else "single_zone"
    sla_field = "sla_single" if zone_scope == "single_zone" else "sla_multi"

    return {"regions": regions, "azs": azs,
            "az_by_region": {k: sorted(v) for k, v in az_by_region.items()},
            "warnings": warnings, "zone_scope": zone_scope, "sla_field": sla_field}


def expand_regions(locations: list) -> set:
    return resolve_placement(locations)["regions"]


# =====================================================================
# 3. PARSE TOSCA TEMPLATE  ->  per-node requests
# =====================================================================
NODE_TYPE_TO_SERVICE = {
    "tosca.nodes.compute": "compute", "compute": "compute", "computewithnetwork": "compute",
    "computewithblocstorage": "compute", "computewithblocnetwork": "compute",
    "tosca.nodes.network.network": "network", "network": "network", "networkforcontainer": "network",
    "dbms": "database",
    "loadbalancer": "loadbalancer",
    "tosca.nodes.storage.objectstorage": "object_storage", "objectstorage": "object_storage",
    "storageforcontainer": "object_storage",
    "tosca.nodes.storage.blockstorage": "block_storage", "blockstorage": "block_storage",
}


@dataclass
class ResourceRequest:
    node_name: str
    node_type: str
    service_type: str
    locations: list = field(default_factory=list)
    distribution: str = "multi_region"
    min_availability: Optional[float] = None
    max_cost: Optional[float] = None
    latency_ms: Optional[float] = None     # recorded, NOT filtered
    providers: list = field(default_factory=list)   # required providers (constraint)
    specs: dict = field(default_factory=dict)
    availability_zones: list = field(default_factory=list)
    az_by_region: dict = field(default_factory=dict)
    placement_warnings: list = field(default_factory=list)
    sla_field: Optional[str] = None        # 'sla_single' | 'sla_multi' (derived from placement)
    notes: dict = field(default_factory=dict)   # e.g. how engine/version were inferred


def _scalar_gb(v):
    """'4 GB'->4.0 ; '40 GB'->40 ; 1024 MB->1.0 ; bare number -> as is."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]*)", str(v))
    if not m:
        return None
    n = float(m.group(1)); unit = m.group(2).upper()
    return n / 1024 if unit == "MB" else (n * 1024 if unit == "TB" else n)


def _scalar_ms(v):
    if v is None:
        return None
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]*)", str(v))
    if not m:
        return None
    n = float(m.group(1)); unit = m.group(2).lower()
    return n * 1000 if unit == "s" else n   # ms by default


def _caps(node):
    return node.get("capabilities", {}) or {}


def _cap_props(node, cap):
    return ((_caps(node).get(cap) or {}).get("properties")) or {}


ENGINE_ALIASES = {
    "postgresql": "postgresql", "postgres": "postgresql", "psql": "postgresql",
    "pgsql": "postgresql", "pg": "postgresql",
    "mysql": "mysql",
    "mariadb": "mariadb", "maria": "mariadb",
    "mongodb": "mongodb", "mongo": "mongodb",
    "sqlserver": "sqlserver", "mssql": "sqlserver",
    "oracle": "oracle", "redis": "redis",
}


def _infer_engine(text: str):
    """Find an engine keyword inside a free text (e.g. the node name). Longest keyword first."""
    t = (text or "").lower()
    for kw in sorted(ENGINE_ALIASES, key=len, reverse=True):
        if kw in t:
            return ENGINE_ALIASES[kw], kw
    return None, None


def _infer_engine_version(node_name: str, props: dict):
    """
    Resolve (engine, version) for a DBMS node.
    Priority: explicit property -> keyword/number found in the node name.
    Version is only inferred from the name once the engine is known.
    Returns (engine, version, notes_dict).
    """
    notes = {}
    engine = (props.get("engine") or "").strip().lower() or None
    kw = None
    if engine:
        notes["engine"] = "from property"
    else:
        engine, kw = _infer_engine(node_name)
        if engine:
            notes["engine"] = f"inferred from node name ('{kw}')"

    version = None
    for pkey in ("version", "component_version", "engine_version", "db_version"):
        pv = props.get(pkey)
        if pv not in (None, ""):
            version = str(pv).strip()
            notes["version"] = f"from property '{pkey}'"
            break
    if not version and engine:  # fallback: look for a number in the name, after the engine keyword
        region = (node_name or "").lower()
        if kw and kw in region:
            region = region[region.index(kw) + len(kw):]
        m = re.search(r"(\d+(?:\.\d+)*)", region)
        if m:
            version = m.group(1)
            notes["version"] = "inferred from node name"
    return engine, version, notes


def extract_requests(template: dict) -> tuple[list[ResourceRequest], list[dict]]:
    topo = template.get("topology_template", {}) or {}
    nodes = topo.get("node_templates", {}) or {}
    policies = topo.get("policies", []) or []

    # policies indexed by target node ; without targets => global
    by_target = defaultdict(list)
    global_pols = []
    for entry in policies:
        # each policy may be {name: {...}} or {...}
        body = list(entry.values())[0] if (isinstance(entry, dict) and len(entry) == 1
                                           and isinstance(list(entry.values())[0], dict)
                                           and "type" in list(entry.values())[0]) else entry
        targets = body.get("targets") or []
        if targets:
            for t in targets:
                by_target[t].append(body)
        else:
            global_pols.append(body)

    requests, skipped = [], []
    for name, node in nodes.items():
        ntype = str(node.get("type", ""))
        st = NODE_TYPE_TO_SERVICE.get(ntype.lower())
        if st is None:
            skipped.append({"node_name": name, "node_type": ntype, "reason": "non-matchable type"})
            continue

        req = ResourceRequest(node_name=name, node_type=ntype, service_type=st)

        # ---- technical requirements by type ----
        props = node.get("properties", {}) or {}

        # provider constraint (node property 'provider' / 'providers')
        _prov = props.get("provider") or props.get("providers")
        if _prov:
            req.providers = list(_prov) if isinstance(_prov, (list, tuple)) else [_prov]

        if st == "compute":
            host = _cap_props(node, "host"); osc = _cap_props(node, "os")
            req.specs = {k: v for k, v in {
                "num_cpus": host.get("num_cpus"),
                "mem_gb": _scalar_gb(host.get("mem_size")),
                "disk_gb": _scalar_gb(host.get("disk_size")),
                "architecture": osc.get("architecture"),
                "os_type": (osc.get("type") or "").lower() or None,
                "os_distribution": (osc.get("distribution") or "").lower() or None,
            }.items() if v not in (None, "")}
        elif st == "database":
            engine, version, dbnotes = _infer_engine_version(name, props)
            req.specs = {k: v for k, v in {"engine": engine, "version": version}.items() if v not in (None, "")}
            if dbnotes:
                req.notes["database"] = dbnotes
        elif st == "network":
            req.specs = {k: v for k, v in {
                "ip_version": ("ipv%s" % props["ip_version"]) if props.get("ip_version") in (4, 6, "4", "6") else props.get("ip_version"),
                "layer": props.get("layer"),
            }.items() if v not in (None, "")}
        elif st == "loadbalancer":
            req.specs = {k: v for k, v in {"lb_type": props.get("lb_type") or props.get("algorithm")}.items() if v}
        elif st == "block_storage":
            req.specs = {k: v for k, v in {"min_capacity_gb": _scalar_gb(props.get("size"))}.items() if v not in (None, "")}
        elif st == "object_storage":
            # object storage is billed per GB -> we need the requested size to get a monthly price
            req.specs = {k: v for k, v in {"size_gb": _scalar_gb(props.get("size"))}.items() if v not in (None, "")}

        # ---- policies (targeting this node or global) ----
        for pol in by_target.get(name, []) + global_pols:
            ptype = str(pol.get("type", "")).lower()
            pp = pol.get("properties", {}) or {}
            if "placement" in ptype:
                req.locations = pp.get("locations", []) or []
                req.distribution = pp.get("distribution", req.distribution)
            elif "availability" in ptype:
                req.min_availability = _f(pp.get("availability"))
            elif "cost" in ptype:
                req.max_cost = _f(pp.get("max_cost"))
            elif "latency" in ptype:
                req.latency_ms = _scalar_ms(pp.get("max_latency"))
            elif "provider" in ptype:
                pv = pp.get("provider") or pp.get("providers")
                if pv:
                    req.providers = list(pv) if isinstance(pv, (list, tuple)) else [pv]

        # ---- placement resolution (AZ wins, single/multi-zone scope) ----
        res = resolve_placement(req.locations, req.distribution)
        req.availability_zones = sorted(res["azs"])
        req.az_by_region = res["az_by_region"]
        req.placement_warnings = res["warnings"]
        req.sla_field = res["sla_field"]

        requests.append(req)
    return requests, skipped


# =====================================================================
# 4. MATCHING
# =====================================================================
def _version_supported(requested, supported: list) -> bool:
    """Lenient version match: exact, or same major (so '8' matches '8.0'/'8.4', '16' matches '16')."""
    rv = str(requested).strip()
    if rv in supported:
        return True
    rmaj = rv.split(".")[0]
    return any(str(s).split(".")[0] == rmaj for s in supported)


def _tech_ok(st, req, o: Offer) -> bool:
    s = o.specs
    if st == "compute":
        if req.get("num_cpus") and (s["cpu"] or 0) < req["num_cpus"]: return False
        if req.get("mem_gb") and (s["memory_gb"] or 0) < req["mem_gb"]: return False
        if req.get("architecture") and _norm(req["architecture"]) != _norm(s["architecture"]): return False
        if req.get("os_type") and _norm(req["os_type"]) not in _norm_set(s["os_type"]): return False
        if req.get("os_distribution") and _norm(req["os_distribution"]) not in _norm_set(s["os_distribution"]): return False
        return True
    if st == "database":
        if req.get("engine") and _norm(req["engine"]) != _norm(s["engine"]): return False
        if req.get("version") and not _version_supported(req["version"], s["versions"]): return False
        return True
    if st == "network":
        if req.get("ip_version") and _norm(req["ip_version"]) not in _norm_set(s["ip_version"]): return False
        if req.get("layer") and _norm(req["layer"]) != _norm(s["layer"]): return False
        return True
    if st == "loadbalancer":
        if req.get("lb_type") and _norm(req["lb_type"]) != _norm(s["lb_type"]): return False
        return True
    if st in ("block_storage", "object_storage"):
        cap = s.get("capacity_gb")
        if req.get("min_capacity_gb") and cap is not None and cap < req["min_capacity_gb"]: return False
        return True
    return True


def _tech_reason(st, specs, pool) -> str:
    """Pinpoint which technical requirement eliminates all offers, with the limiting value."""
    checks = []  # (label, requested, satisfied_count, info)

    def numeric(reqkey, offkey):
        vals = [o.specs.get(offkey) for o in pool if o.specs.get(offkey) is not None]
        sat = sum(1 for v in vals if v >= specs[reqkey])
        info = f"max available={max(vals)}" if vals else "no data"
        checks.append((reqkey, specs[reqkey], sat, info))

    def member(reqkey, offkey):
        opts = set()
        for o in pool:
            v = o.specs.get(offkey)
            opts |= set(v) if isinstance(v, (list, set)) else ({v} if v else set())
        sat = sum(1 for o in pool
                  if specs[reqkey] in (o.specs.get(offkey) if isinstance(o.specs.get(offkey), (list, set)) else {o.specs.get(offkey)}))
        checks.append((reqkey, specs[reqkey], sat, f"available={sorted(o for o in opts if o)}"))

    if st == "compute":
        if specs.get("num_cpus") is not None: numeric("num_cpus", "cpu")
        if specs.get("mem_gb") is not None: numeric("mem_gb", "memory_gb")
        if specs.get("architecture"): member("architecture", "architecture")
        if specs.get("os_type"): member("os_type", "os_type")
        if specs.get("os_distribution"): member("os_distribution", "os_distribution")
    elif st == "database":
        if specs.get("engine"): member("engine", "engine")
        if specs.get("version"):
            sat = sum(1 for o in pool if _version_supported(specs["version"], o.specs.get("versions") or []))
            checks.append(("version", specs["version"], sat, "see supported_versions"))
    elif st == "network":
        if specs.get("ip_version"): member("ip_version", "ip_version")
        if specs.get("layer"): member("layer", "layer")
    elif st == "loadbalancer":
        if specs.get("lb_type"): member("lb_type", "lb_type")
    elif st in ("block_storage", "object_storage"):
        if specs.get("min_capacity_gb") is not None: numeric("min_capacity_gb", "capacity_gb")

    killers = [c for c in checks if c[2] == 0]
    if killers:
        return "; ".join(f"requirement {lbl}={req} not satisfiable ({info})" for lbl, req, _, info in killers)
    if checks:
        return ("no single offer meets all technical requirements at once: "
                + ", ".join(f"{lbl}={req}" for lbl, req, _, _ in checks))
    return "technical requirements not satisfied"


def effective_price(o: Offer, req: ResourceRequest) -> Optional[float]:
    """Monthly price comparable to the user's budget.
    - object_storage: billed per GB -> price_gb * requested size_gb.
      Returns None if the node gives no size (budget can't be enforced).
    - everything else: the offer's monthly price."""
    if o.service_type == "object_storage":
        pg = o.specs.get("price_gb")
        size = req.specs.get("size_gb")
        if pg is not None and size is not None:
            return round(pg * size, 4)
        return None
    return o.price_month


def match(req: ResourceRequest, cat: Catalog) -> list[Offer]:
    allowed = expand_regions(req.locations)
    sla_attr = req.sla_field or ("sla_multi" if req.distribution == "multi_region" else "sla_single")
    prov = {_norm(p) for p in req.providers} if req.providers else None
    out = []
    for o in cat.by_type.get(req.service_type, []):
        if allowed and o.region not in allowed: continue
        if prov and _norm(o.provider) not in prov: continue
        sla = getattr(o, sla_attr)
        # Missing SLA (None): the offer is NOT dropped (value cannot be verified).
        if req.min_availability is not None and sla is not None and sla < req.min_availability: continue
        price = effective_price(o, req)
        if req.max_cost is not None and price is not None and price > req.max_cost: continue
        if not _tech_ok(req.service_type, req.specs, o): continue
        out.append((o, price))
    out.sort(key=lambda op: (op[1] if op[1] is not None else float("inf")))
    return [o for o, _ in out]


def diagnose(req: ResourceRequest, cat: Catalog) -> dict:
    """Funnel: how many offers survive AFTER each filter, plus a readable reason."""
    allowed = expand_regions(req.locations)
    sla_attr = req.sla_field or ("sla_multi" if req.distribution == "multi_region" else "sla_single")
    prov = {_norm(p) for p in req.providers} if req.providers else None
    pool0 = cat.by_type.get(req.service_type, [])
    f = {"in_registry": len(pool0)}

    pool_region = [o for o in pool0 if (not allowed or o.region in allowed)]
    f["after_region"] = len(pool_region)

    pool_prov = pool_region
    if prov:
        pool_prov = [o for o in pool_region if _norm(o.provider) in prov]
    f["after_provider"] = len(pool_prov)

    pool_sla = pool_prov
    if req.min_availability is not None:
        # Missing SLA (None) -> keep the offer (cannot be verified, not eliminated).
        pool_sla = [o for o in pool_prov
                    if (getattr(o, sla_attr) is None or getattr(o, sla_attr) >= req.min_availability)]
    f["after_sla"] = len(pool_sla)

    pool_cost = pool_sla
    if req.max_cost is not None:
        pool_cost = [o for o in pool_sla
                     if (effective_price(o, req) is None or effective_price(o, req) <= req.max_cost)]
    f["after_cost"] = len(pool_cost)

    pool_tech = [o for o in pool_cost if _tech_ok(req.service_type, req.specs, o)]
    f["after_tech"] = len(pool_tech)

    # first stage that drops to 0
    killer = None
    prev = f["in_registry"]
    for stage in ("after_region", "after_provider", "after_sla", "after_cost", "after_tech"):
        if f[stage] == 0 and prev > 0:
            killer = stage
            break
        prev = f[stage]
    f["eliminated_by"] = killer

    # ---- readable message with the limiting value ----
    reason = None
    if killer == "after_region":
        reason = f"No '{req.service_type}' offer in region(s) {sorted(allowed) or 'requested'}."
    elif killer == "after_provider":
        avail = sorted({o.provider for o in pool_region})
        reason = (f"No offer from provider(s) {req.providers} in the requested region(s). "
                  f"Providers present here: {avail}.")
    elif killer == "after_sla":
        slas = [getattr(o, sla_attr) for o in pool_region if getattr(o, sla_attr) is not None]
        best = max(slas) if slas else None
        zone_note = (" (single-zone because one AZ is pinned; the multi-zone SLA would be higher)"
                     if sla_attr == "sla_single" and req.availability_zones else "")
        reason = (f"Requested availability {req.min_availability}% > best available SLA "
                  f"{best}% (field {sla_attr}) across the {len(pool_region)} regional offer(s){zone_note}.")
    elif killer == "after_cost":
        prices = [effective_price(o, req) for o in pool_sla if effective_price(o, req) is not None]
        cheapest = min(prices) if prices else None
        unit = "/month (price_gb x size_gb)" if req.service_type == "object_storage" else "/month"
        reason = (f"Budget {req.max_cost}/month < cheapest offer {cheapest}{unit} "
                  f"among the {len(pool_sla)} remaining offer(s).")
    elif killer == "after_tech":
        reason = _tech_reason(req.service_type, req.specs, pool_cost)
    f["reason"] = reason
    return f


# =====================================================================
# 4bis. CONFLICT ANALYSIS (independent) + REGISTRY-BACKED SUGGESTIONS
# =====================================================================
# Principle: instead of a sequential funnel (which always blames the LAST
# filter), every criterion is tested INDEPENDENTLY on each offer. We get a
# per-offer "mask": which criteria pass. Then, via "leave-one-out": if
# relaxing A SINGLE criterion brings back at least one offer, that criterion
# is a possible relaxation. If several criteria each have this power ->
# COMBINED conflict (relax either one, e.g. high cost vs high spec, or
# criterion vs provider).

# numeric specs: request key -> offer key
_NUMERIC_SPEC = {"num_cpus": "cpu", "mem_gb": "memory_gb", "min_capacity_gb": "capacity_gb"}
# "membership" specs: request key -> offer key
_MEMBER_SPEC = {"architecture": "architecture", "os_type": "os_type",
                "os_distribution": "os_distribution", "engine": "engine",
                "version": "versions", "ip_version": "ip_version",
                "layer": "layer", "lb_type": "lb_type"}


def _spec_pass(st, key, val, o: Offer) -> bool:
    """A single technical criterion, tested alone on one offer (with normalisation)."""
    s = o.specs
    if key == "num_cpus":          return (s.get("cpu") or 0) >= val
    if key == "mem_gb":            return (s.get("memory_gb") or 0) >= val
    if key == "min_capacity_gb":
        cap = s.get("capacity_gb"); return cap is None or cap >= val
    if key == "version":           return _version_supported(val, s.get("versions") or [])
    if key in _MEMBER_SPEC:
        offv = s.get(_MEMBER_SPEC[key])
        if isinstance(offv, (list, set, tuple)):
            return _norm(val) in _norm_set(offv)
        return _norm(val) == _norm(offv)
    return True


def _spec_suggest(st, key, val, survivors: list) -> dict:
    """Achievable value for this criterion, computed from REAL offers."""
    if key in _NUMERIC_SPEC:
        offkey = _NUMERIC_SPEC[key]
        vals = [o.specs.get(offkey) for o in survivors if o.specs.get(offkey) is not None]
        best = max(vals) if vals else None
        return {"action": "lower_spec", "spec": key, "requested": val,
                "achievable_max": best, "based_on_offers": len(vals),
                "detail": f"Lower '{key}' from {val} to <= {best} (maximum present in the registry)."}
    offkey = _MEMBER_SPEC.get(key, key)
    opts = set()
    for o in survivors:
        v = o.specs.get(offkey)
        if isinstance(v, (list, set, tuple)):
            opts |= {x for x in v if x}
        elif v:
            opts.add(v)
    opts = sorted(opts)
    label = "propose other versions" if key == "version" else \
            "propose what exists" if key == "engine" else "change the value"
    return {"action": "change_spec_value", "spec": key, "requested": val,
            "available": opts, "based_on_offers": len(survivors),
            "detail": f"{label} for '{key}': available values {opts}."}


def _build_criteria(req: ResourceRequest, allowed: set, sla_attr: str) -> list:
    """List of ACTIVE criteria, each = {key, passes(o), suggest(survivors)}."""
    crits = []

    # --- region ---
    if allowed:
        crits.append({
            "key": "region",
            "passes": (lambda o, A=allowed: o.region in A),
            "suggest": (lambda S: {
                "action": "change_region",
                "available_regions": sorted({o.region for o in S}),
                "based_on_offers": len(S),
                "detail": "Propose another region: offers are present in "
                          f"{sorted({o.region for o in S})}."}),
        })

    # --- provider ---
    if req.providers:
        prov = {_norm(p) for p in req.providers}
        crits.append({
            "key": "provider",
            "passes": (lambda o, P=prov: _norm(o.provider) in P),
            "suggest": (lambda S: {
                "action": "change_provider",
                "requested": req.providers,
                "available_providers": sorted({o.provider for o in S}),
                "based_on_offers": len(S),
                "detail": "Change the provider (or the criterion): these providers "
                          f"work: {sorted({o.provider for o in S})}."}),
        })

    # --- SLA (None = passes, not verifiable) ---
    if req.min_availability is not None:
        def _sla_suggest(S, attr=sla_attr, mn=req.min_availability):
            slas = [getattr(o, attr) for o in S if getattr(o, attr) is not None]
            best = max(slas) if slas else None
            return {"action": "lower_availability", "requested": mn,
                    "achievable_max": best, "based_on_offers": len(S),
                    "detail": f"Propose other SLA values: lower from {mn}% "
                              f"to <= {best}% (best real SLA available)."}
        crits.append({
            "key": "sla",
            "passes": (lambda o, attr=sla_attr, mn=req.min_availability:
                       getattr(o, attr) is None or getattr(o, attr) >= mn),
            "suggest": _sla_suggest,
        })

    # --- cost ---
    if req.max_cost is not None:
        def _cost_suggest(S, mx=req.max_cost):
            prices = [effective_price(o, req) for o in S]
            prices = [p for p in prices if p is not None]
            cheapest = min(prices) if prices else None
            return {"action": "increase_budget", "requested": mx,
                    "cheapest_available": cheapest, "based_on_offers": len(S),
                    "detail": f"Propose another cost: raise the budget from {mx} "
                              f"to >= {cheapest} (cheapest offer that satisfies the rest)."}
        crits.append({
            "key": "cost",
            "passes": (lambda o, mx=req.max_cost:
                       effective_price(o, req) is None or effective_price(o, req) <= mx),
            "suggest": _cost_suggest,
        })

    # --- technical specs (one criterion per requested spec) ---
    for skey, sval in (req.specs or {}).items():
        if skey in ("size_gb",):   # object_storage: used for pricing, not a hard filter
            continue
        crits.append({
            "key": f"spec:{skey}",
            "passes": (lambda o, k=skey, v=sval: _spec_pass(req.service_type, k, v, o)),
            "suggest": (lambda S, k=skey, v=sval: _spec_suggest(req.service_type, k, v, S)),
        })

    return crits


def analyze_conflicts(req: ResourceRequest, cat: Catalog) -> dict:
    """Detect conflicts (hard / combined) and propose relaxations that are
    GUARANTEED by real offers from the registry."""
    allowed = expand_regions(req.locations)
    sla_attr = req.sla_field or ("sla_multi" if req.distribution == "multi_region" else "sla_single")
    pool = cat.by_type.get(req.service_type, [])

    if not pool:
        return {"status": "no_service_in_catalog",
                "message": f"No offer of type '{req.service_type}' in the registry "
                           f"(service not supported or empty registry)."}

    crits = _build_criteria(req, allowed, sla_attr)
    if not crits:
        return {"status": "ok", "candidate_count": len(pool)}

    keys = [c["key"] for c in crits]
    crit_by_key = {c["key"]: c for c in crits}

    # per-offer mask: which criteria pass
    masks = [(o, {c["key"]: c["passes"](o) for c in crits}) for o in pool]

    full = [o for o, m in masks if all(m.values())]
    if full:
        return {"status": "ok", "candidate_count": len(full)}

    # how many offers satisfy each criterion individually?
    sat_count = {k: sum(1 for _, m in masks if m[k]) for k in keys}

    # leave-one-out: does relaxing THIS single criterion bring back offers?
    single_relax = {}
    for k in keys:
        survivors = [o for o, m in masks if all(m[j] for j in keys if j != k)]
        if survivors:
            sug = dict(crit_by_key[k]["suggest"](survivors))
            sug["criterion"] = k
            sug["is_hard"] = (sat_count[k] == 0)  # no offer passes this criterion at all
            single_relax[k] = sug

    options = list(single_relax.values())

    if len(single_relax) >= 2:
        conflict_type = "combined"
        resolution = ("COMBINED conflict: no offer satisfies everything at once, "
                      "but relaxing A SINGLE one of the criteria below (your choice) is enough.")
    elif len(single_relax) == 1:
        conflict_type = "single"
        resolution = "A single criterion blocks: relaxing it is enough."
    else:
        # no simple relaxation: at least 2 criteria must be relaxed together
        conflict_type = "deep"
        resolution = ("DEEP conflict: relaxing a single criterion is not enough, "
                      "at least two must be loosened at the same time.")
        # for information, achievable values criterion by criterion over the whole pool
        for k in keys:
            survivors = [o for o, m in masks if m[k]]  # offers passing at least this criterion
            if not survivors:
                survivors = pool
            sug = dict(crit_by_key[k]["suggest"](survivors))
            sug["criterion"] = k
            sug["is_hard"] = (sat_count[k] == 0)
            options.append(sug)

    return {
        "status": "no_candidate",
        "conflict_type": conflict_type,
        "blocking_criteria": list(single_relax.keys()) or keys,
        "resolution": resolution,
        "criteria_individually_satisfiable": sat_count,
        "options": options,
    }


# =====================================================================
# 5. PIPELINE -> JSON
# =====================================================================
def run(template: dict, cat: Catalog, template_name: str = "") -> dict:
    requests, skipped = extract_requests(template)
    result = {"template": template_name,
              "description": template.get("description", "").strip(),
              "catalog_summary": cat.summary(),
              "nodes": [], "skipped_nodes": skipped}
    for req in requests:
        cands = match(req, cat)
        sla_attr = req.sla_field or ("sla_multi" if req.distribution == "multi_region" else "sla_single")
        result["nodes"].append({
            "node_name": req.node_name,
            "node_type": req.node_type,
            "service_type": req.service_type,
            "extracted_requirements": req.specs,
            "extraction_notes": req.notes,
            "applied_filters": {
                "regions": sorted(expand_regions(req.locations)) or "any",
                "providers": req.providers or "any",
                "target_availability_zones": req.availability_zones or "any (whole region)",
                "az_by_region": req.az_by_region,
                "distribution": req.distribution,
                "zone_scope": "single_zone" if sla_attr == "sla_single" else "multi_zone",
                "sla_field_used": sla_attr,
                "min_availability": req.min_availability,
                "max_cost_month": req.max_cost,
                "latency_ms_recorded_not_filtered": req.latency_ms,
            },
            "placement_warnings": req.placement_warnings,
            "candidate_count": len(cands),
            "filter_funnel": diagnose(req, cat),
            "conflict_analysis": analyze_conflicts(req, cat),
            "candidates": [dict(o.columns,
                                deploy_in_az=req.az_by_region.get(o.region, "whole region"),
                                estimated_price_month=effective_price(o, req),
                                sla_verified=(getattr(o, sla_attr) is not None))
                           for o in cands],
        })
    return result


from functools import lru_cache


@lru_cache(maxsize=None)
def _load_registries_cached(registries_folder: str) -> Catalog:
    """Load taxonomy + catalog ONLY ONCE per folder (the .xlsx reads are cached).
    The Catalog is only READ afterwards (never mutated by run/match), so returning
    the same instance across calls is safe."""
    load_taxonomy(registries_folder)
    return load_catalog(registries_folder)


def clear_registry_cache() -> None:
    """Call this if the .xlsx files change at runtime (otherwise the old catalog
    keeps being served from the cache)."""
    _load_registries_cached.cache_clear()


def discover_candidates(tosca_template, registries_folder: str = None,
                        template_name: str = "") -> dict:
    """Entry point called by agent_graph.py.
    Accepts the TOSCA YAML (str) OR an already-parsed dict, loads the catalog +
    taxonomy from <src>/registries/ (cached), and returns the candidates dict."""
    import os, yaml
    template = yaml.safe_load(tosca_template) if isinstance(tosca_template, str) else tosca_template
    if not template:
        return {"nodes": [], "skipped_nodes": [], "error": "empty TOSCA template"}
    if registries_folder is None:
        # ./registries located next to this module (src/registries/)
        registries_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registries")
    cat = _load_registries_cached(registries_folder)
    return run(template, cat, template_name=template_name)


def main():
    ap = argparse.ArgumentParser(description="TOSCA template -> JSON of provider candidate offers")
    ap.add_argument("template", help="TOSCA template file (.yaml/.yml/.json)")
    ap.add_argument("--registries", default=".", help="folder containing the _en.xlsx registries")
    ap.add_argument("--out", default=None, help="output JSON file (otherwise stdout)")
    args = ap.parse_args()

    import yaml
    with open(args.template, encoding="utf-8") as fh:
        template = yaml.safe_load(fh)

    cat = load_catalog(args.registries)
    from_file = load_taxonomy(args.registries)
    print(f"[taxonomy] {'loaded from region_taxonomy.xlsx' if from_file else 'embedded table (file absent)'}",
          file=sys.stderr)
    result = run(template, cat, template_name=args.template)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"OK -> {args.out}  ({sum(n['candidate_count'] for n in result['nodes'])} total candidates)")
    else:
        print(text)


if __name__ == "__main__":
    main()