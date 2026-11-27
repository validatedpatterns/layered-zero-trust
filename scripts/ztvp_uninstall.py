#!/usr/bin/env python3
"""Safely drive and audit the Layered Zero Trust Pattern uninstall.

This tool uses the installed `oc` CLI and Python's standard library only.
`snapshot` must be run before ZTVP is installed if the final audit is expected
to distinguish pre-existing cluster resources from installation residue.
For an existing installation without that baseline, use `inventory` followed by
`uninstall --inventory ... --best-effort`; that path protects likely or
ambiguous pre-existing resources but cannot prove ownership or restore original
cluster trust settings.
For ACM spokes, select each spoke context and run `snapshot` before installation
and `audit` after uninstall as well; the Pattern Operator's spoke phase is
monitored from the hub, but this process cannot use hidden ACM kubeconfig secrets.

Typical use:
  python3 scripts/ztvp_uninstall.py snapshot --output ztvp-preinstall-baseline.json
  python3 scripts/ztvp_uninstall.py uninstall --baseline ztvp-preinstall-baseline.json \
      --pattern layered-zero-trust \
      --root-application vp-gitops/layered-zero-trust-hub
  # Review the plan and its exact confirmation string, then repeat with:
  # --execute --ack-preflight --expected-server <oc-whoami-show-server> \
  # --confirm '<printed string>'
  python3 scripts/ztvp_uninstall.py audit --baseline ztvp-preinstall-baseline.json \
      --pre-uninstall ztvp-uninstall-artifacts/pre-uninstall.json
  python3 scripts/ztvp_uninstall.py verify-reinstall \
      --expected-server <oc-whoami-show-server> --wait-seconds 600
For an existing Pattern without a baseline:
  python3 scripts/ztvp_uninstall.py inventory --output ztvp-current-inventory.json
  python3 scripts/ztvp_uninstall.py uninstall --inventory ztvp-current-inventory.json \
      --best-effort --pattern layered-zero-trust \
      --root-application vp-gitops/layered-zero-trust-hub

The script deliberately does not clear finalizers, delete namespaces, or
remove OLM-retained APIs automatically. Those actions can orphan data or
break other workloads; the script records exact blockers/candidates for an
administrator to review. Before starting the Argo cascade, it also detects
resources that existed before the Pattern but are now tracked by its Argo
Application tree. Baseline-mode execution is blocked until those resources are
protected from deletion. In inventory mode, likely pre-existing and ambiguous
tracked resources receive temporary deletion protection automatically.
`verify-reinstall` is read-only and checks the Vault pod, ClusterSecretStore,
qtodo ExternalSecrets, and their Argo Applications after a new installation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import functools
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PATTERN_RESOURCE = "patterns.gitops.hybrid-cloud-patterns.io"
MIN_OPERATOR_VERSION = (0, 0, 65)
COLLECTIONS = {
    "patterns": (PATTERN_RESOURCE, True),
    "applications": ("applications.argoproj.io", True),
    "subscriptions": ("subscriptions.operators.coreos.com", True),
    "csvs": ("clusterserviceversions.operators.coreos.com", True),
    "operatorgroups": ("operatorgroups.operators.coreos.com", True),
    "namespaces": ("namespaces", False),
    "crds": ("customresourcedefinitions.apiextensions.k8s.io", False),
    "apiservices": ("apiservices.apiregistration.k8s.io", False),
    "managedclusters": ("managedclusters.cluster.open-cluster-management.io", False),
    "pvcs": ("persistentvolumeclaims", True),
    "pvs": ("persistentvolumes", False),
}
KNOWN_ZTVP_TRUST_CONFIGMAPS = {
    "proxy": "ztvp-proxy-ca",
    "image": "ztvp-registry-cas",
}


class OcError(RuntimeError):
    def __init__(self, args: list[str], returncode: int, stderr: str):
        self.args_used = args
        self.returncode = returncode
        self.stderr = stderr.strip()
        super().__init__(f"oc {' '.join(args)} failed: {self.stderr}")


def oc(args: list[str], *, allow_missing: bool = False) -> str:
    command = ["oc", *args]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode == 0:
        return result.stdout
    message = result.stderr or result.stdout
    missing = any(
        phrase in message.lower()
        for phrase in ("not found", "doesn't have a resource type", "no matches for kind")
    )
    if allow_missing and missing:
        return ""
    raise OcError(args, result.returncode, message)


def oc_json(args: list[str], *, allow_missing: bool = False) -> Any | None:
    output = oc([*args, "-o", "json"], allow_missing=allow_missing)
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"oc returned invalid JSON for {' '.join(args)}: {error}") from error


def items(document: Any | None) -> list[dict[str, Any]]:
    if not document:
        return []
    if document.get("kind") == "List" or "items" in document:
        return list(document.get("items", []))
    return [document]


def get_collection(resource: str, *, all_namespaces: bool) -> tuple[list[dict[str, Any]], str | None]:
    args = ["get", resource]
    if all_namespaces:
        args.append("-A")
    try:
        return items(oc_json(args, allow_missing=True)), None
    except OcError as error:
        return [], str(error)


def meta_summary(obj: dict[str, Any]) -> dict[str, Any]:
    meta = obj.get("metadata", {})
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "uid": meta.get("uid"),
        "creationTimestamp": meta.get("creationTimestamp"),
    }


def resource_ref(item: dict[str, Any]) -> str:
    namespace = item.get("namespace")
    name = item.get("name", "<unnamed>")
    return f"{namespace}/{name}" if namespace else name


def app_summary(obj: dict[str, Any]) -> dict[str, Any]:
    meta = obj.get("metadata", {})
    labels = meta.get("labels", {}) or {}
    annotations = meta.get("annotations", {}) or {}
    automated = (obj.get("spec", {}).get("syncPolicy", {}) or {}).get("automated")
    status_resources = obj.get("status", {}).get("resources", []) or []
    tracked = []
    for item in status_resources:
        tracked.append(
            {
                "group": item.get("group", ""),
                "version": item.get("version", ""),
                "kind": item.get("kind", ""),
                "namespace": item.get("namespace"),
                "name": item.get("name"),
            }
        )
    return {
        **meta_summary(obj),
        "labels": {
            key: labels[key]
            for key in (
                "argocd.argoproj.io/instance",
                "app.kubernetes.io/instance",
                "app.kubernetes.io/part-of",
            )
            if key in labels
        },
        "trackingId": annotations.get("argocd.argoproj.io/tracking-id"),
        "finalizers": meta.get("finalizers", []) or [],
        "automatedSync": automated is not None and automated.get("enabled", True) is not False,
        "syncStatus": obj.get("status", {}).get("sync", {}).get("status"),
        "healthStatus": obj.get("status", {}).get("health", {}).get("status"),
        "resources": tracked,
    }


def csv_summary(obj: dict[str, Any]) -> dict[str, Any]:
    spec = obj.get("spec", {})
    status = obj.get("status", {})
    owned = spec.get("customresourcedefinitions", {}).get("owned", []) or []
    return {
        **meta_summary(obj),
        "version": status.get("version"),
        "phase": status.get("phase"),
        "ownedCRDs": [entry.get("name") for entry in owned if entry.get("name")],
    }


def subscription_summary(obj: dict[str, Any]) -> dict[str, Any]:
    spec = obj.get("spec", {})
    return {
        **meta_summary(obj),
        "package": spec.get("name"),
        "channel": spec.get("channel"),
        "source": spec.get("source"),
    }


def crd_summary(obj: dict[str, Any]) -> dict[str, Any]:
    spec = obj.get("spec", {})
    names = spec.get("names", {})
    return {
        **meta_summary(obj),
        "group": spec.get("group"),
        "plural": names.get("plural"),
        "kind": names.get("kind"),
        "scope": spec.get("scope"),
    }


def apiservice_summary(obj: dict[str, Any]) -> dict[str, Any]:
    spec = obj.get("spec", {})
    service = spec.get("service") or {}
    available = None
    for condition in obj.get("status", {}).get("conditions", []) or []:
        if condition.get("type") == "Available":
            available = condition.get("status") == "True"
    return {
        **meta_summary(obj),
        "group": spec.get("group"),
        "version": spec.get("version"),
        "serviceNamespace": service.get("namespace"),
        "serviceName": service.get("name"),
        "available": available,
    }


def namespace_summary(obj: dict[str, Any]) -> dict[str, Any]:
    labels = obj.get("metadata", {}).get("labels", {}) or {}
    return {
        **meta_summary(obj),
        "argocdManagedBy": labels.get("argocd.argoproj.io/managed-by"),
        "phase": obj.get("status", {}).get("phase"),
        "finalizers": obj.get("spec", {}).get("finalizers", []) or [],
    }


def pvc_summary(obj: dict[str, Any]) -> dict[str, Any]:
    spec = obj.get("spec", {})
    return {
        **meta_summary(obj),
        "phase": obj.get("status", {}).get("phase"),
        "storageClassName": spec.get("storageClassName"),
        "volumeName": spec.get("volumeName"),
    }


def pv_summary(obj: dict[str, Any]) -> dict[str, Any]:
    spec = obj.get("spec", {})
    claim = spec.get("claimRef") or {}
    return {
        **meta_summary(obj),
        "phase": obj.get("status", {}).get("phase"),
        "reclaimPolicy": spec.get("persistentVolumeReclaimPolicy"),
        "claim": f"{claim.get('namespace')}/{claim.get('name')}" if claim else None,
    }


def cluster_identity() -> dict[str, str]:
    return {
        "context": oc(["config", "current-context"]).strip(),
        "user": oc(["whoami"]).strip(),
        "server": oc(["whoami", "--show-server"]).strip(),
    }


def require_admin() -> None:
    answer = oc(["auth", "can-i", "*", "*", "--all-namespaces"]).strip().lower()
    if answer != "yes":
        raise RuntimeError("The current identity does not have cluster-admin-equivalent permissions.")


def get_singleton(resource: str, name: str) -> dict[str, Any] | None:
    try:
        return oc_json(["get", resource, name], allow_missing=True)
    except OcError:
        raise


def cr_identity(obj: dict[str, Any]) -> dict[str, Any]:
    meta = obj.get("metadata", {})
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "uid": meta.get("uid"),
        "deletionTimestamp": meta.get("deletionTimestamp"),
        "finalizers": meta.get("finalizers", []) or [],
    }


def scan_custom_resources(
    crds: list[dict[str, Any]], workers: int
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """List object identities for every CRD; never save custom-resource bodies."""
    jobs: list[tuple[str, str, bool]] = []
    for crd in crds:
        spec = crd.get("spec", {})
        names = spec.get("names", {})
        group, plural = spec.get("group"), names.get("plural")
        if group and plural:
            jobs.append((crd.get("metadata", {}).get("name", ""), f"{plural}.{group}", spec.get("scope") == "Namespaced"))

    def scan(job: tuple[str, str, bool]) -> tuple[str, list[dict[str, Any]], str | None]:
        crd_name, resource, namespaced = job
        args = ["get", resource]
        if namespaced:
            args.append("-A")
        try:
            # A CRD is known to exist, so a missing/unavailable endpoint is a
            # scan error rather than an empty resource collection.
            data = oc_json(args, allow_missing=False)
            return crd_name, [cr_identity(obj) for obj in items(data)], None
        except OcError as error:
            return crd_name, [], str(error)
        except RuntimeError as error:
            return crd_name, [], str(error)

    result: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for crd_name, identities, error in pool.map(scan, jobs):
            result[crd_name] = identities
            if error:
                errors.append(f"{crd_name}: {error}")
    return result, errors


def inventory(*, workers: int) -> dict[str, Any]:
    identity = cluster_identity()
    result: dict[str, Any] = {
        "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cluster": identity,
        "resources": {},
        "customResourceInstances": {},
        "scanErrors": [],
    }
    raw: dict[str, list[dict[str, Any]]] = {}
    for key, (resource, all_ns) in COLLECTIONS.items():
        objects, error = get_collection(resource, all_namespaces=all_ns)
        raw[key] = objects
        if error:
            result["scanErrors"].append(f"{resource}: {error}")

    result["resources"]["patterns"] = [
        {
            **meta_summary(obj),
            "deletionTimestamp": obj.get("metadata", {}).get("deletionTimestamp"),
            "finalizers": obj.get("metadata", {}).get("finalizers", []) or [],
            "deletionPhase": obj.get("status", {}).get("deletionPhase"),
            "lastStep": obj.get("status", {}).get("lastStep"),
            "lastError": obj.get("status", {}).get("lastError"),
        }
        for obj in raw["patterns"]
    ]
    result["resources"]["applications"] = [app_summary(obj) for obj in raw["applications"]]
    result["resources"]["subscriptions"] = [subscription_summary(obj) for obj in raw["subscriptions"]]
    result["resources"]["csvs"] = [csv_summary(obj) for obj in raw["csvs"]]
    result["resources"]["operatorgroups"] = [meta_summary(obj) for obj in raw["operatorgroups"]]
    result["resources"]["namespaces"] = [namespace_summary(obj) for obj in raw["namespaces"]]
    result["resources"]["crds"] = [crd_summary(obj) for obj in raw["crds"]]
    result["resources"]["apiservices"] = [apiservice_summary(obj) for obj in raw["apiservices"]]
    result["resources"]["pvcs"] = [pvc_summary(obj) for obj in raw["pvcs"]]
    result["resources"]["pvs"] = [pv_summary(obj) for obj in raw["pvs"]]
    result["resources"]["managedclusters"] = [
        {
            **meta_summary(obj),
            "available": any(
                condition.get("type") == "ManagedClusterConditionAvailable"
                and condition.get("status") == "True"
                for condition in obj.get("status", {}).get("conditions", [])
            ),
        }
        for obj in raw["managedclusters"]
    ]

    for name, resource in (("proxy", "proxies.config.openshift.io"), ("image", "images.config.openshift.io")):
        try:
            obj = get_singleton(resource, "cluster")
            spec = (obj or {}).get("spec", {})
            field = "trustedCA" if name == "proxy" else "additionalTrustedCA"
            result["resources"][name] = {field: spec.get(field)} if obj else None
        except OcError as error:
            result["scanErrors"].append(f"{resource}: {error}")
            result["resources"][name] = None

    cr_instances, cr_errors = scan_custom_resources(raw["crds"], workers)
    result["customResourceInstances"] = cr_instances
    result["scanErrors"].extend(cr_errors)
    return result


def write_json(path: Path, document: Any, *, exclusive: bool = False) -> None:
    parent_existed = path.parent.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not parent_existed:
        os.chmod(path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(path, 0o600)


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_version(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = re.search(r"(?:v)?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def operator_version(override: str | None) -> str | None:
    if override:
        return override
    csvs, _ = get_collection("clusterserviceversions.operators.coreos.com", all_namespaces=True)
    for obj in csvs:
        meta = obj.get("metadata", {})
        name = meta.get("name", "")
        if "patterns-operator" in name.lower() or "validated-pattern" in name.lower():
            version = obj.get("status", {}).get("version") or name
            if parse_version(version):
                return version
    deployments, error = get_collection("deployments.apps", all_namespaces=True)
    if not error:
        for deployment in deployments:
            meta = deployment.get("metadata", {})
            if "patterns-operator" not in meta.get("name", "").lower():
                continue
            for container in deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
                image = container.get("image", "")
                if "patterns-operator" in image.lower():
                    tag = image.rsplit(":", 1)[-1]
                    if parse_version(tag):
                        return tag
    return None


def ensure_operator_version(value: str | None) -> None:
    version = parse_version(value)
    if version is None:
        raise RuntimeError(
            "Could not determine the Patterns Operator version. Supply --operator-version after checking the controller image/CSV."
        )
    if version < MIN_OPERATOR_VERSION:
        raise RuntimeError(f"Patterns Operator {value} is older than required 0.0.65; upgrade it before uninstalling.")


def key(summary: dict[str, Any]) -> str:
    namespace, name = summary.get("namespace"), summary.get("name")
    return f"{namespace}/{name}" if namespace else str(name)


def app_tree(apps: list[dict[str, Any]], root: str, *, allow_missing_root: bool = False) -> list[dict[str, Any]]:
    by_key = {key(app): app for app in apps}
    if root not in by_key and not allow_missing_root:
        raise RuntimeError(f"Root Argo CD Application {root!r} was not found; specify --root-application namespace/name.")
    selected = {root}
    selected_names = {root.split("/", 1)[-1]}
    changed = True
    while changed:
        changed = False
        refs = selected | selected_names
        for app_key, app in by_key.items():
            if app_key in selected:
                continue
            labels = app.get("labels", {})
            candidates = {
                labels.get("argocd.argoproj.io/instance"),
                labels.get("app.kubernetes.io/instance"),
                labels.get("app.kubernetes.io/part-of"),
            }
            tracking_id = app.get("trackingId") or ""
            if ":" in tracking_id:
                candidates.add(tracking_id.split(":", 1)[0])
            if candidates & refs:
                selected.add(app_key)
                selected_names.add(app_key.split("/", 1)[-1])
                changed = True
    return [app for app in apps if key(app) in selected]


def find_pattern(patterns: list[dict[str, Any]], name: str | None, namespace: str | None) -> dict[str, Any]:
    candidates = [obj for obj in patterns if (name is None or obj.get("name") == name) and (namespace is None or obj.get("namespace") == namespace)]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one target Pattern, found {len(candidates)}. Specify --pattern and --namespace.")
    return candidates[0]


def check_baseline_cluster(baseline: dict[str, Any], current: dict[str, str]) -> None:
    if baseline.get("cluster", {}).get("server") != current.get("server"):
        raise RuntimeError("Saved inventory API server does not match the current oc context; refusing to continue.")


def added(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    before_ids = {item.get("uid") or key(item) for item in before}
    return [item for item in after if (item.get("uid") or key(item)) not in before_ids]


def inventory_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Summarize inventory-to-post-uninstall changes without claiming ownership."""
    categories = (
        "patterns", "applications", "subscriptions", "csvs", "operatorgroups", "namespaces",
        "crds", "apiservices", "pvcs", "pvs", "managedclusters",
    )
    result: dict[str, Any] = {}
    for category in categories:
        old = before.get("resources", {}).get(category, []) or []
        new = after.get("resources", {}).get(category, []) or []
        old_ids = {item.get("uid") or key(item) for item in old}
        new_ids = {item.get("uid") or key(item) for item in new}
        result[category] = {
            "atInventory": len(old),
            "stillPresent": len(old_ids & new_ids),
            "removed": len(old_ids - new_ids),
            "appearedSinceInventory": [
                {key_name: item.get(key_name) for key_name in ("name", "namespace", "uid", "creationTimestamp")}
                for item in new if (item.get("uid") or key(item)) not in old_ids
            ],
        }

    old_crs = before.get("customResourceInstances", {}) or {}
    new_crs = after.get("customResourceInstances", {}) or {}
    old_ids = {
        (crd, item.get("uid") or resource_ref(item))
        for crd, entries in old_crs.items() for item in entries
    }
    new_ids = {
        (crd, item.get("uid") or resource_ref(item))
        for crd, entries in new_crs.items() for item in entries
    }
    appeared = []
    for crd, entries in new_crs.items():
        for item in entries:
            if (crd, item.get("uid") or resource_ref(item)) not in old_ids:
                appeared.append({"crd": crd, **item})
    result["customResourceInstances"] = {
        "atInventory": len(old_ids),
        "stillPresent": len(old_ids & new_ids),
        "removed": len(old_ids - new_ids),
        "appearedSinceInventory": appeared,
    }
    return result


def app_resource_probe(
    resource: dict[str, Any], removed_crd_kinds: set[tuple[str, str]] | None = None
) -> dict[str, Any]:
    kind, name = resource.get("kind"), resource.get("name")
    if not kind or not name:
        return {**resource, "state": "unknown", "error": "missing kind/name in Argo status"}
    try:
        api_resource = api_resource_name(
            resource.get("group") or "", kind, resource.get("version")
        )
    except Exception as error:
        if (resource.get("group") or "", kind) in (removed_crd_kinds or set()):
            return {
                **resource,
                "state": "absent",
                "verification": "owning CRD was removed since the pre-uninstall inventory",
            }
        return {**resource, "state": "unknown", "error": f"could not resolve API resource: {error}"}
    args = ["get", api_resource, name]
    if resource.get("namespace"):
        args.extend(["-n", resource["namespace"]])
    args.extend(["--ignore-not-found=true"])
    try:
        output = oc(args)
        if not output.strip():
            return {**resource, "state": "absent"}
        try:
            obj = json.loads(oc([*args[:-1], "-o", "json"]))
            metadata = obj.get("metadata", {})
            annotations = metadata.get("annotations", {}) or {}
            tracking_id = annotations.get("argocd.argoproj.io/tracking-id")
            last_applied = annotations.get("kubectl.kubernetes.io/last-applied-configuration", "")
            return {
                **resource,
                "state": "present",
                "apiResource": api_resource,
                "uid": metadata.get("uid"),
                "creationTimestamp": metadata.get("creationTimestamp"),
                "trackingId": tracking_id,
                "syncOptions": annotations.get("argocd.argoproj.io/sync-options"),
                "managedBy": (metadata.get("labels", {}) or {}).get("argocd.argoproj.io/managed-by"),
                "lastAppliedContainsTrackingId": bool(tracking_id and tracking_id in last_applied),
                "finalizers": metadata.get("finalizers", []) or [],
            }
        except Exception:
            return {**resource, "state": "present"}
    except OcError as error:
        return {**resource, "state": "unknown", "error": error.stderr}


@functools.lru_cache(maxsize=None)
def api_resource_name(group: str, kind: str, version: str | None) -> str:
    """Resolve a resource using its exact API group/version, avoiding Kind ambiguity."""
    output = oc(["api-resources", f"--api-group={group}", "-o", "json"])
    try:
        resources = json.loads(output).get("resources", [])
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid api-resources JSON for group {group!r}: {error}") from error
    matches = [
        item
        for item in resources
        if item.get("kind") == kind and (not version or item.get("version") == version)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one API resource for {group or 'core'}/{version or '*'}/{kind}, found {len(matches)}"
        )
    name = matches[0].get("name")
    if not name:
        raise RuntimeError(f"API resource name missing for {group or 'core'}/{kind}")
    return f"{name}.{group}" if group else name


def removed_crd_kinds(before: dict[str, Any], after: dict[str, Any]) -> set[tuple[str, str]]:
    """Return served CRD kinds that were present before uninstall and are gone now."""
    before_kinds = {
        (item.get("group") or "", item.get("kind") or "")
        for item in before.get("resources", {}).get("crds", [])
        if item.get("kind")
    }
    after_kinds = {
        (item.get("group") or "", item.get("kind") or "")
        for item in after.get("resources", {}).get("crds", [])
        if item.get("kind")
    }
    return before_kinds - after_kinds


def probe_app_resources(
    apps: list[dict[str, Any]],
    workers: int,
    *,
    removed_crd_kinds: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    resources: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    for app in apps:
        for item in app.get("resources", []):
            identity = (item.get("kind", ""), item.get("namespace"), item.get("name", ""))
            if identity[0] and identity[2]:
                entry = resources.setdefault(identity, {**item, "trackedByApps": []})
                app_key = key(app)
                if app_key not in entry["trackedByApps"]:
                    entry["trackedByApps"].append(app_key)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(
            pool.map(
                lambda item: app_resource_probe(item, removed_crd_kinds),
                resources.values(),
            )
        )


def parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def baseline_resource_uids(baseline: dict[str, Any]) -> dict[tuple[str, str | None, str], str]:
    """Index resources present in the pre-install inventory by Kubernetes identity."""
    collections = {
        "patterns": "Pattern",
        "applications": "Application",
        "subscriptions": "Subscription",
        "csvs": "ClusterServiceVersion",
        "operatorgroups": "OperatorGroup",
        "namespaces": "Namespace",
        "crds": "CustomResourceDefinition",
        "apiservices": "APIService",
        "pvcs": "PersistentVolumeClaim",
        "pvs": "PersistentVolume",
        "managedclusters": "ManagedCluster",
    }
    result: dict[tuple[str, str | None, str], str] = {}
    resources = baseline.get("resources", {})
    for collection, kind in collections.items():
        for item in resources.get(collection, []) or []:
            name = item.get("name")
            if name and item.get("uid"):
                result[(kind, item.get("namespace"), name)] = item["uid"]

    kind_by_crd = {
        item.get("name"): item.get("kind")
        for item in resources.get("crds", []) or []
        if item.get("name") and item.get("kind")
    }
    for crd_name, instances in (baseline.get("customResourceInstances", {}) or {}).items():
        kind = kind_by_crd.get(crd_name)
        if not kind:
            continue
        for item in instances or []:
            name = item.get("name")
            if name and item.get("uid"):
                result[(kind, item.get("namespace"), name)] = item["uid"]
    return result


def find_preexisting_tracked_resources(
    baseline: dict[str, Any],
    pattern: dict[str, Any],
    apps: list[dict[str, Any]],
    probed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find Argo-tracked objects that existed before this Pattern was created."""
    created_at = parse_timestamp(pattern.get("creationTimestamp"))
    baseline_uids = baseline_resource_uids(baseline)
    baseline_namespaces = {
        item.get("name"): item
        for item in baseline.get("resources", {}).get("namespaces", []) or []
        if item.get("name")
    }
    apps_by_key = {key(app): app for app in apps}
    found = []
    for item in probed:
        if item.get("state") != "present":
            continue
        identity = (item.get("kind", ""), item.get("namespace"), item.get("name", ""))
        baseline_uid = baseline_uids.get(identity)
        same_baseline_object = bool(baseline_uid and baseline_uid == item.get("uid"))
        item_created = parse_timestamp(item.get("creationTimestamp"))
        created_before_pattern = bool(created_at and item_created and item_created < created_at)
        if not same_baseline_object and not created_before_pattern:
            continue

        sync_options = {
            token.strip()
            for token in (item.get("syncOptions") or "").split(",")
            if token.strip()
        }
        owners = [apps_by_key.get(owner) for owner in item.get("trackedByApps", [])]
        automated_owners = [key(owner) for owner in owners if owner and owner.get("automatedSync")]
        found.append(
            {
                "kind": item.get("kind"),
                "namespace": item.get("namespace"),
                "name": item.get("name"),
                "uid": item.get("uid"),
                "creationTimestamp": item.get("creationTimestamp"),
                "apiResource": item.get("apiResource"),
                "trackingId": item.get("trackingId"),
                "syncOptions": item.get("syncOptions"),
                "managedBy": item.get("managedBy"),
                "trackedByApps": item.get("trackedByApps", []),
                "matchedPreinstallUid": same_baseline_object,
                "createdBeforePattern": created_before_pattern,
                "preinstallManagedBy": baseline_namespaces.get(item.get("name"), {}).get("argocdManagedBy"),
                "preinstallManagedByKnown": "argocdManagedBy" in baseline_namespaces.get(item.get("name"), {}),
                "deleteProtected": "Delete=false" in sync_options,
                "automatedSyncOwners": automated_owners,
            }
        )
    return found


def record_preexisting_resource_state(
    path: Path,
    cluster: dict[str, str],
    target_pattern: str,
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Save original sync options before an administrator adds Delete=false."""
    prior: dict[str, Any] = {}
    if path.exists():
        prior = read_json(path)
        if prior.get("cluster", {}).get("server") != cluster.get("server"):
            raise RuntimeError("Pre-existing-resource state belongs to a different cluster.")
        if prior.get("targetPattern") != target_pattern:
            raise RuntimeError("Pre-existing-resource state belongs to a different Pattern.")

    previous = {
        (item.get("kind"), item.get("namespace"), item.get("name")): item
        for item in prior.get("resources", [])
    }
    recorded = dict(previous)
    for item in resources:
        identity = (item.get("kind"), item.get("namespace"), item.get("name"))
        old = previous.get(identity)
        if old:
            if old.get("uid") != item.get("uid"):
                raise RuntimeError(
                    f"Pre-existing resource {resource_ref(item)} changed UID since the plan was recorded. Rerun review."
                )
            item["syncOptionsBeforeProtection"] = old.get("syncOptionsBeforeProtection")
            continue

        current_options = item.get("syncOptions")
        if "Delete=false" in {token.strip() for token in (current_options or "").split(",")}:
            raise RuntimeError(
                f"{item.get('kind')} {resource_ref(item)} already has Delete=false, but its original sync options were not recorded."
            )
        state = {
            "kind": item.get("kind"),
            "namespace": item.get("namespace"),
            "name": item.get("name"),
            "uid": item.get("uid"),
            "apiResource": item.get("apiResource"),
            "syncOptionsBeforeProtection": current_options,
            "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        recorded[identity] = state
        item["syncOptionsBeforeProtection"] = current_options

    write_json(
        path,
        {
            "cluster": cluster,
            "targetPattern": target_pattern,
            "resources": list(recorded.values()),
        },
    )
    return resources


def release_preexisting_resources(
    resources: list[dict[str, Any]],
    apps: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    """Remove temporary deletion protection and this Pattern's Argo metadata."""
    app_names = {app.get("name") for app in apps if app.get("name")}
    app_namespaces = {app.get("namespace") for app in apps if app.get("namespace")}
    outcomes: list[dict[str, Any]] = []

    for item in resources:
        name = item.get("name")
        api_resource = item.get("apiResource")
        namespace = item.get("namespace")
        if not name or not api_resource:
            outcomes.append({**item, "cleanupState": "unknown", "reason": "missing API resource identity"})
            continue

        args = ["get", api_resource, name]
        if namespace:
            args.extend(["-n", namespace])
        try:
            live = oc_json(args, allow_missing=True)
        except OcError as error:
            outcomes.append({**item, "cleanupState": "error", "reason": error.stderr})
            continue
        if not live:
            outcomes.append({**item, "cleanupState": "absent"})
            continue

        metadata = live.get("metadata", {})
        if metadata.get("uid") != item.get("uid"):
            outcomes.append(
                {**item, "cleanupState": "conflict", "reason": "live UID differs from the pre-uninstall UID"}
            )
            continue

        annotations = metadata.get("annotations", {}) or {}
        labels = metadata.get("labels", {}) or {}
        annotation_patch: dict[str, Any] = {}
        label_patch: dict[str, Any] = {}
        sync_key = "argocd.argoproj.io/sync-options"
        tracking_key = "argocd.argoproj.io/tracking-id"
        last_applied_key = "kubectl.kubernetes.io/last-applied-configuration"
        current_sync = annotations.get(sync_key)
        original_sync = item.get("syncOptionsBeforeProtection")
        current_sync_values = {
            token.strip()
            for token in (current_sync or "").split(",")
            if token.strip()
        }
        original_sync_values = {
            token.strip()
            for token in (original_sync or "").split(",")
            if token.strip()
        }
        if current_sync != original_sync:
            expected_protected_values = original_sync_values | {"Delete=false"}
            if "Delete=false" in current_sync_values and current_sync_values == expected_protected_values:
                annotation_patch[sync_key] = original_sync
            else:
                outcomes.append(
                    {**item, "cleanupState": "conflict", "reason": "sync-options changed after the preflight plan"}
                )
                continue

        current_tracking = annotations.get(tracking_key)
        if (
            current_tracking
            and current_tracking == item.get("trackingId")
            and current_tracking.split(":", 1)[0] in app_names
        ):
            annotation_patch[tracking_key] = None
            last_applied = annotations.get(last_applied_key, "")
            if current_tracking in last_applied:
                annotation_patch[last_applied_key] = None

        managed_by = labels.get("argocd.argoproj.io/managed-by")
        if (
            item.get("kind") == "Namespace"
            and item.get("preinstallManagedByKnown")
            and item.get("preinstallManagedBy") is None
            and managed_by in app_namespaces
        ):
            label_patch["argocd.argoproj.io/managed-by"] = None

        if not annotation_patch and not label_patch:
            outcomes.append({**item, "cleanupState": "already-clean"})
            continue

        patch: dict[str, Any] = {"metadata": {}}
        if annotation_patch:
            patch["metadata"]["annotations"] = annotation_patch
        if label_patch:
            patch["metadata"]["labels"] = label_patch
        patch_args = [
            "patch",
            api_resource,
            name,
            "--type=merge",
            "-p",
            json.dumps(patch, separators=(",", ":")),
        ]
        if namespace:
            patch_args.extend(["-n", namespace])
        try:
            oc(patch_args)
            outcomes.append({**item, "cleanupState": "released"})
        except OcError as error:
            outcomes.append({**item, "cleanupState": "error", "reason": error.stderr})
    return outcomes


def restore_known_cluster_fields(
    baseline: dict[str, Any],
    post: dict[str, Any],
    *,
    proxy_configmap: str,
    image_configmap: str,
) -> list[dict[str, Any]]:
    """Restore only fields still set to ZTVP's known ConfigMap names."""
    outcomes: list[dict[str, Any]] = []
    for area, field, resource, expected_name in (
        ("proxy", "trustedCA", "proxies.config.openshift.io", proxy_configmap),
        ("image", "additionalTrustedCA", "images.config.openshift.io", image_configmap),
    ):
        original = baseline.get("resources", {}).get(area)
        current = post.get("resources", {}).get(area)
        if original is None or current is None:
            outcomes.append({"resource": area, "state": "unknown", "reason": "baseline or live object unavailable"})
            continue
        original_value = original.get(field)
        current_value = current.get(field)
        if current_value == original_value:
            outcomes.append({"resource": area, "state": "unchanged"})
            continue
        if (current_value or {}).get("name") != expected_name:
            outcomes.append(
                {
                    "resource": area,
                    "state": "conflict",
                    "reason": f"current {field} is not the known ZTVP value {expected_name!r}; left unchanged",
                    "current": current_value,
                    "baseline": original_value,
                }
            )
            continue
        patch = {"spec": {field: original_value}}
        try:
            oc(["patch", resource, "cluster", "--type=merge", "-p", json.dumps(patch, separators=(",", ":"))])
            outcomes.append({"resource": area, "state": "restored", "from": current_value, "to": original_value})
        except OcError as error:
            outcomes.append({"resource": area, "state": "error", "reason": str(error)})
    return outcomes


def cleanup_known_trust_configmaps(
    baseline: dict[str, Any],
    post: dict[str, Any],
    pattern: dict[str, Any],
    *,
    proxy_configmap: str,
    image_configmap: str,
) -> list[dict[str, Any]]:
    """Remove only ZTVP-created trust maps that are no longer referenced."""
    outcomes: list[dict[str, Any]] = []
    pattern_created = parse_timestamp(pattern.get("creationTimestamp"))
    for area, field, name in (
        ("proxy", "trustedCA", proxy_configmap),
        ("image", "additionalTrustedCA", image_configmap),
    ):
        if not name:
            continue
        original = baseline.get("resources", {}).get(area) or {}
        live_config = post.get("resources", {}).get(area) or {}
        if (original.get(field) or {}).get("name") == name:
            outcomes.append({"resource": f"ConfigMap/openshift-config/{name}", "state": "pre-existing"})
            continue
        if (live_config.get(field) or {}).get("name") == name:
            outcomes.append(
                {
                    "resource": f"ConfigMap/openshift-config/{name}",
                    "state": "still-referenced",
                    "reason": f"{area.title()}/cluster still references this ConfigMap",
                }
            )
            continue
        try:
            configmap = oc_json(
                ["get", "configmaps", name, "-n", "openshift-config"], allow_missing=True
            )
        except OcError as error:
            outcomes.append({"resource": f"ConfigMap/openshift-config/{name}", "state": "error", "reason": error.stderr})
            continue
        if not configmap:
            outcomes.append({"resource": f"ConfigMap/openshift-config/{name}", "state": "absent"})
            continue

        metadata = configmap.get("metadata", {})
        labels = metadata.get("labels", {}) or {}
        owned_labels = (
            labels.get("app.kubernetes.io/name") == "ztvp-certificates"
            and labels.get("app.kubernetes.io/managed-by") == "ztvp-certificate-manager"
        )
        created = parse_timestamp(metadata.get("creationTimestamp"))
        if not pattern_created or not created or created < pattern_created or not owned_labels:
            outcomes.append(
                {
                    "resource": f"ConfigMap/openshift-config/{name}",
                    "state": "conflict",
                    "reason": "creation time or ZTVP certificate-manager labels do not prove ownership",
                }
            )
            continue
        try:
            oc(["delete", "configmaps", name, "-n", "openshift-config", "--wait=true"])
            outcomes.append({"resource": f"ConfigMap/openshift-config/{name}", "state": "deleted"})
        except OcError as error:
            outcomes.append({"resource": f"ConfigMap/openshift-config/{name}", "state": "error", "reason": error.stderr})
    return outcomes


def disable_automatic_sync(apps: list[dict[str, Any]], root: str) -> None:
    """Freeze the target Argo tree immediately before deleting the Pattern.

    The Pattern/root reconciliation may reapply Application specs after an
    earlier manual patch, so do this only after the expensive inventory checks
    and immediately before starting Pattern deletion.
    """
    patch = json.dumps({"spec": {"syncPolicy": {"automated": None}}}, separators=(",", ":"))

    def disable_one(app: dict[str, Any]) -> None:
        name, namespace = app.get("name"), app.get("namespace")
        if not name or not namespace:
            raise RuntimeError("Cannot disable automatic sync for an Application with an incomplete identity.")
        live = oc_json(["get", "applications.argoproj.io", name, "-n", namespace])
        if (live.get("spec", {}).get("syncPolicy", {}) or {}).get("automated") is not None:
            oc(["patch", "applications.argoproj.io", name, "-n", namespace, "--type=merge", "-p", patch])

    def disable_many(group: list[dict[str, Any]]) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(1, len(group)))) as pool:
            list(pool.map(disable_one, group))

    root_apps = [app for app in apps if key(app) == root]
    child_apps = sorted((app for app in apps if key(app) != root), key=key)
    if len(root_apps) != 1:
        raise RuntimeError(f"Expected one root Application {root}; found {len(root_apps)}.")

    for _attempt in range(3):
        # The root can reapply child Application specs while it remains active.
        # Disable the children in parallel, disable the root, then make one
        # final child pass before verifying the whole tree.
        disable_many(child_apps)
        disable_one(root_apps[0])
        disable_many(child_apps)
        time.sleep(2)
        still_automated = []
        for app in apps:
            live = oc_json(["get", "applications.argoproj.io", app["name"], "-n", app["namespace"]])
            if (live.get("spec", {}).get("syncPolicy", {}) or {}).get("automated") is not None:
                still_automated.append(key(app))
        if not still_automated:
            print(f"Automatic sync disabled and verified on {len(apps)} target Applications.")
            return
    raise RuntimeError(
        "Automatic sync was restored while freezing the Argo tree; Pattern deletion was not started: "
        + ", ".join(still_automated)
    )


def enable_pattern_pruning(name: str, namespace: str) -> None:
    """Set the operator's explicit opt-in required by its delete webhook."""
    annotation = "patterns.gitops.hybrid-cloud-patterns.io/prune"
    live = get_pattern(name, namespace)
    if live is None:
        raise RuntimeError("Pattern disappeared before the prune annotation could be set.")
    metadata = live.get("metadata", {})
    uid = metadata.get("uid")
    if (metadata.get("annotations") or {}).get(annotation) != "true":
        patch = {"metadata": {"annotations": {annotation: "true"}}}
        oc(
            [
                "patch",
                PATTERN_RESOURCE,
                name,
                "-n",
                namespace,
                "--type=merge",
                "-p",
                json.dumps(patch, separators=(",", ":")),
            ]
        )
    verified = get_pattern(name, namespace)
    if (
        verified is None
        or verified.get("metadata", {}).get("uid") != uid
        or (verified.get("metadata", {}).get("annotations") or {}).get(annotation) != "true"
    ):
        raise RuntimeError("Could not verify the Pattern prune opt-in; Pattern deletion was not started.")
    print("Pattern prune opt-in enabled and verified.")


def write_inventory_files(outdir: Path, name: str, data: dict[str, Any]) -> None:
    ensure_private_dir(outdir)
    write_json(outdir / f"{name}.json", data)


def ensure_private_dir(path: Path) -> None:
    existed = path.exists()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not existed:
        os.chmod(path, 0o700)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError(f"Artifact directory {path} must not be accessible by group/other; chmod it to 700.")


def make_report(
    baseline: dict[str, Any] | None,
    before: dict[str, Any],
    after: dict[str, Any],
    target_pattern: str,
    target_apps: list[dict[str, Any]],
    app_probe: list[dict[str, Any]],
    trust_actions: list[dict[str, Any]],
    preexisting_tracked: list[dict[str, Any]] | None = None,
    preexisting_cleanup: list[dict[str, Any]] | None = None,
    *,
    comparison_mode: str = "pre-install-baseline",
) -> dict[str, Any]:
    after_resources = after.get("resources", {})
    baseline_resources = (baseline or {}).get("resources", {})
    target_app_keys = {key(app) for app in target_apps}
    remaining_apps = [app for app in after_resources.get("applications", []) if key(app) in target_app_keys]
    pre_namespaces = baseline_resources.get("namespaces", [])
    post_namespaces = after_resources.get("namespaces", [])
    pre_crds = baseline_resources.get("crds", [])
    post_crds = after_resources.get("crds", [])
    pre_apiservices = baseline_resources.get("apiservices", [])
    post_apiservices = after_resources.get("apiservices", [])
    pre_subs = baseline_resources.get("subscriptions", [])
    post_subs = after_resources.get("subscriptions", [])
    pre_csvs = baseline_resources.get("csvs", [])
    post_csvs = after_resources.get("csvs", [])
    pre_groups = baseline_resources.get("operatorgroups", [])
    post_groups = after_resources.get("operatorgroups", [])

    cr_instance_deltas: list[dict[str, Any]] = []
    baseline_crs = (baseline or {}).get("customResourceInstances", {})
    after_crs = after.get("customResourceInstances", {})
    if comparison_mode == "pre-install-baseline":
        for crd_name, post_items in after_crs.items():
            old_ids = {item.get("uid") or resource_ref(item) for item in baseline_crs.get(crd_name, [])}
            for item in post_items:
                if (item.get("uid") or resource_ref(item)) not in old_ids:
                    cr_instance_deltas.append({"crd": crd_name, **item})

    unavailable_spokes = [
        item for item in before.get("resources", {}).get("managedclusters", []) if item.get("available") is False
    ]
    preexisting_ids = {
        (item.get("kind"), item.get("namespace"), item.get("name"), item.get("uid"))
        for item in (preexisting_tracked or [])
    }
    for item in app_probe:
        identity = (item.get("kind"), item.get("namespace"), item.get("name"), item.get("uid"))
        if item.get("state") == "present" and identity in preexisting_ids:
            item["state"] = "pre-existing-preserved"
            item["reason"] = (
                "Inventory ownership assessment retained this resource from the Argo cascade"
                if comparison_mode == "current-install-inventory"
                else "UID matches a pre-install resource retained from the Argo cascade"
            )
    trust_checks = {}
    for area, field in (("proxy", "trustedCA"), ("image", "additionalTrustedCA")):
        original = baseline_resources.get(area)
        current = after_resources.get(area)
        trust_checks[area] = {
            "matchesPreinstall": (
                None if comparison_mode == "current-install-inventory" else bool(
                    original is not None and current is not None and original.get(field) == current.get(field)
                )
            ),
            "preinstall": original.get(field) if original is not None else None,
            "current": current.get(field) if current is not None else None,
        }

    new_since_preinstall = None
    if comparison_mode == "pre-install-baseline":
        new_since_preinstall = {
            "namespaces": added(pre_namespaces, post_namespaces),
            "subscriptions": added(pre_subs, post_subs),
            "csvs": added(pre_csvs, post_csvs),
            "operatorgroups": added(pre_groups, post_groups),
            "crds": added(pre_crds, post_crds),
            "apiservices": added(pre_apiservices, post_apiservices),
            "pvcs": added(baseline_resources.get("pvcs", []), after_resources.get("pvcs", [])),
            "pvs": added(baseline_resources.get("pvs", []), after_resources.get("pvs", [])),
            "managedclusters": added(
                baseline_resources.get("managedclusters", []), after_resources.get("managedclusters", [])
            ),
            "customResourceInstances": cr_instance_deltas,
        }

    report = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cluster": after.get("cluster"),
        "comparisonMode": comparison_mode,
        "targetPattern": target_pattern,
        "patternAbsent": not any(key(item) == target_pattern for item in after_resources.get("patterns", [])),
        "targetApplicationsRemaining": [key(app) for app in remaining_apps],
        "patternManagedResources": app_probe,
        "preexistingTrackedResources": preexisting_tracked or [],
        "preexistingResourceCleanup": preexisting_cleanup or [],
        "managedClustersUnavailableAtPreflight": unavailable_spokes,
        "clusterTrust": trust_checks,
        "newSincePreinstall": new_since_preinstall,
        "clusterTrustRestoration": trust_actions,
        "scanErrors": sorted(set(
            (baseline or {}).get("scanErrors", []) + before.get("scanErrors", []) + after.get("scanErrors", [])
        )),
        "strictZeroResidue": False,
        "strictZeroResidueNote": "",
    }
    if comparison_mode == "current-install-inventory":
        report["inventoryComparison"] = inventory_comparison(before, after)
        report["strictZeroResidueNote"] = (
            "No pre-install baseline was available. Review inventoryComparison and all remaining OLM/shared resources; "
            "pre-install deltas and original Proxy/Image trust values are unknown. The ownership assessment is heuristic, "
            "and the script leaves ambiguous cluster-wide resources for administrator review."
        )
    else:
        report["strictZeroResidueNote"] = (
            "Review every new CRD, APIService, Subscription, CSV, namespace, and custom-resource instance. "
            "Review pre-existing resources adopted by Argo and remove stale Pattern tracking metadata. "
            "The script never deletes OLM-retained or ambiguous resources automatically."
        )
    return report


def require_delete_permission(namespace: str) -> None:
    answer = oc(["auth", "can-i", "delete", PATTERN_RESOURCE, "-n", namespace]).strip().lower()
    if answer != "yes":
        raise RuntimeError(f"Current identity cannot delete {PATTERN_RESOURCE} in namespace {namespace!r}.")


def capture_operator_logs(outdir: Path, *, since: str = "1h") -> list[str]:
    deployments, error = get_collection("deployments.apps", all_namespaces=True)
    failures: list[str] = []
    if error:
        return [error]
    targets = []
    for deployment in deployments:
        meta = deployment.get("metadata", {})
        name = meta.get("name", "")
        namespace = meta.get("namespace", "")
        if "patterns-operator" in name.lower() or ("central" == name and namespace == "stackrox"):
            targets.append((namespace, name))
    for namespace, name in targets:
        try:
            output = oc(["logs", "-n", namespace, f"deployment/{name}", f"--since={since}", "--all-containers=true"])
            safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{namespace}-{name}")
            path = outdir / f"{safe_name}.log"
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(output)
            os.chmod(path, 0o600)
        except OcError as error:
            failures.append(str(error))
    return failures


def save_stalled_diagnostics(outdir: Path, apps: list[dict[str, Any]], workers: int) -> None:
    probe = probe_app_resources(apps, workers)
    write_json(outdir / "stalled-managed-resources.json", probe)
    failures = capture_operator_logs(outdir)
    write_json(outdir / "diagnostic-errors.json", failures)


def discover_root(pattern_name: str, apps: list[dict[str, Any]], requested: str | None) -> str:
    if requested:
        return requested
    candidates = [app for app in apps if app.get("name") == f"{pattern_name}-hub"]
    if len(candidates) == 1:
        return key(candidates[0])
    locations = [key(app) for app in candidates]
    raise RuntimeError(
        "Could not uniquely find the root Argo Application. Pass --root-application namespace/name. "
        f"Candidates: {locations or 'none'}"
    )


def save_progress(path: Path, pattern: dict[str, Any], started: float) -> tuple[str, str | None]:
    status = pattern.get("status", {})
    phase = status.get("deletionPhase") or "Starting"
    error = status.get("lastError")
    state = {
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsedSeconds": round(time.monotonic() - started, 1),
        "phase": phase,
        "lastStep": status.get("lastStep"),
        "lastError": error,
        "deletionTimestamp": pattern.get("metadata", {}).get("deletionTimestamp"),
    }
    write_json(path, state)
    return phase, error


def get_pattern(name: str, namespace: str) -> dict[str, Any] | None:
    try:
        return oc_json(["get", PATTERN_RESOURCE, name, "-n", namespace], allow_missing=True)
    except OcError as error:
        raise RuntimeError(str(error)) from error


def confirm_execution(args: argparse.Namespace, pattern: dict[str, Any], server: str) -> None:
    required = f"DELETE {pattern['metadata']['namespace']}/{pattern['metadata']['name']} on {server}"
    print(f"Type this exact confirmation to start: {required}")
    if args.confirm is not None:
        if args.confirm != required:
            raise RuntimeError("--confirm does not match the required Pattern/cluster confirmation string.")
    elif sys.stdin.isatty():
        typed = input("> ").strip()
        if typed != required:
            raise RuntimeError("Confirmation did not match; no Pattern deletion was started.")
    else:
        raise RuntimeError("Non-interactive execution requires --confirm with the exact string printed above.")


def do_snapshot(args: argparse.Namespace) -> int:
    require_admin()
    data = inventory(workers=args.workers)
    data["inventoryType"] = "pre-install-baseline"
    output = args.output.resolve()
    write_json(output, data, exclusive=not args.overwrite)
    print(f"Pre-install baseline saved: {output}")
    print(f"CRDs inventoried: {len(data['resources'].get('crds', []))}")
    print(f"Custom-resource API scan errors: {len(data['scanErrors'])}")
    if data["scanErrors"]:
        print("Baseline is incomplete; strict zero-residue verification will not be possible without resolving scan errors.")
    return 0


def do_inventory(args: argparse.Namespace) -> int:
    """Save a current cluster inventory for an already-installed Pattern."""
    require_admin()
    data = inventory(workers=args.workers)
    data["inventoryType"] = "current-install-inventory"
    data["trackedResourceInventory"] = probe_app_resources(
        data.get("resources", {}).get("applications", []),
        workers=args.workers,
    )
    output = args.output.resolve()
    write_json(output, data, exclusive=not args.overwrite)
    print(f"Current cluster inventory saved: {output}")
    patterns = data.get("resources", {}).get("patterns", [])
    print(f"Patterns found: {len(patterns)}")
    deleting = [key(item) for item in patterns if item.get("deletionTimestamp")]
    if deleting:
        print(
            "Warning: uninstall is already in progress for "
            + ", ".join(deleting)
            + "; inventory cannot recover resources already removed."
        )
    print(f"Argo Applications inventoried: {len(data.get('resources', {}).get('applications', []))}")
    print(f"Tracked resources identity-checked: {len(data['trackedResourceInventory'])}")
    unknown = sum(
        item.get("state") == "unknown"
        or (item.get("state") == "present" and not item.get("uid"))
        for item in data["trackedResourceInventory"]
    )
    print(f"Tracked resources with unknown identity: {unknown}")
    print(f"CRDs inventoried: {len(data.get('resources', {}).get('crds', []))}")
    print(f"Custom-resource API scan errors: {len(data['scanErrors'])}")
    if data["scanErrors"]:
        print("Inventory is incomplete; resolve scan errors or use the explicit incomplete-inventory override.")
    return 0


def validate_current_inventory(
    snapshot: dict[str, Any], current: dict[str, Any], pattern_name: str | None,
    namespace: str | None, requested_root: str | None, *, allow_resume: bool = False,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if snapshot.get("inventoryType") != "current-install-inventory":
        raise RuntimeError(
            "--inventory must reference a file created by the `inventory` command; "
            "a pre-install baseline cannot be used in inventory mode."
        )
    check_baseline_cluster(snapshot, current.get("cluster", {}))
    saved_pattern = find_pattern(
        snapshot.get("resources", {}).get("patterns", []), pattern_name, namespace
    )
    live_pattern = find_pattern(
        current.get("resources", {}).get("patterns", []), pattern_name, namespace
    )
    if not saved_pattern.get("uid") or saved_pattern.get("uid") != live_pattern.get("uid"):
        raise RuntimeError("The Pattern UID differs from the saved current inventory; recapture inventory and review the plan.")
    pattern_name = saved_pattern["name"]
    root = discover_root(pattern_name, snapshot.get("resources", {}).get("applications", []), requested_root)
    saved_apps = app_tree(snapshot.get("resources", {}).get("applications", []), root)
    live_apps = app_tree(
        current.get("resources", {}).get("applications", []), root,
        allow_missing_root=allow_resume,
    )
    saved_by_key = {key(app): app for app in saved_apps}
    live_by_key = {key(app): app for app in live_apps}
    if (not allow_resume and set(saved_by_key) != set(live_by_key)) or not set(live_by_key).issubset(saved_by_key):
        raise RuntimeError("The Argo Application tree changed since the saved inventory; recapture inventory and review the plan.")
    for app_key, live in live_by_key.items():
        saved = saved_by_key[app_key]
        if not saved.get("uid") or saved.get("uid") != live.get("uid"):
            raise RuntimeError(f"Application {app_key} changed UID since the saved inventory; recapture inventory.")
        saved_resources = {
            (item.get("group"), item.get("version"), item.get("kind"), item.get("namespace"), item.get("name"))
            for item in saved.get("resources", [])
        }
        live_resources = {
            (item.get("group"), item.get("version"), item.get("kind"), item.get("namespace"), item.get("name"))
            for item in live.get("resources", [])
        }
        if not allow_resume and saved_resources != live_resources:
            raise RuntimeError(f"Tracked resources for {app_key} changed since the saved inventory; recapture inventory.")
    return live_pattern, root, (saved_apps if allow_resume else live_apps)


def verify_tracked_resource_inventory(
    snapshot: dict[str, Any], apps: list[dict[str, Any]], live_probe: list[dict[str, Any]]
) -> None:
    saved_probe = snapshot.get("trackedResourceInventory")
    if saved_probe is None:
        raise RuntimeError(
            "The current inventory does not contain tracked resource UIDs; recapture it with this script version."
        )
    app_keys = {key(app) for app in apps}
    saved = {
        (item.get("kind"), item.get("namespace"), item.get("name")): item
        for item in saved_probe
        if set(item.get("trackedByApps", [])) & app_keys
    }
    live = {
        (item.get("kind"), item.get("namespace"), item.get("name")): item
        for item in live_probe
    }
    if set(saved) != set(live):
        raise RuntimeError(
            "The target Argo tree's tracked resources changed since inventory capture; recapture inventory and review the plan."
        )
    for identity, saved_item in saved.items():
        live_item = live[identity]
        if saved_item.get("state") == "unknown":
            raise RuntimeError(
                f"Saved inventory could not establish the state of {saved_item.get('kind')} {resource_ref(saved_item)}."
            )
        if saved_item.get("state") != live_item.get("state") or (
            saved_item.get("state") == "present"
            and (not saved_item.get("uid") or live_item.get("uid") != saved_item.get("uid"))
        ):
            raise RuntimeError(
                f"{saved_item.get('kind')} {resource_ref(saved_item)} changed or is unreadable since inventory capture."
            )


def classify_inventory_tracked_resources(
    pattern: dict[str, Any], apps: list[dict[str, Any]], probed: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Flag tracked resources that should be retained when no pre-install baseline exists."""
    pattern_created = parse_timestamp(pattern.get("creationTimestamp"))
    apps_by_key = {key(app): app for app in apps}
    protected: list[dict[str, Any]] = []
    for item in probed:
        if item.get("state") != "present":
            continue
        item_created = parse_timestamp(item.get("creationTimestamp"))
        if not pattern_created or not item_created or item_created == pattern_created:
            assessment = "ambiguous"
            reason = "Pattern/resource creation time is missing or equal; retained conservatively"
        elif item_created < pattern_created:
            assessment = "likely-pre-existing"
            reason = "Resource creation time predates the Pattern; retained conservatively"
        else:
            assessment = "likely-pattern-created"
            reason = "Resource creation time is after Pattern creation; ownership is still heuristic"
        item["inventoryOwnershipAssessment"] = assessment
        item["inventoryOwnershipReason"] = reason
        item["protectFromCascade"] = assessment in {"likely-pre-existing", "ambiguous"}
        sync_options = {
            token.strip()
            for token in (item.get("syncOptions") or "").split(",")
            if token.strip()
        }
        item["deleteProtected"] = "Delete=false" in sync_options
        item["automatedSyncOwners"] = [
            owner
            for owner in item.get("trackedByApps", [])
            if apps_by_key.get(owner, {}).get("automatedSync")
        ]
        if item["protectFromCascade"]:
            protected.append(item)
    return protected


def append_delete_false(sync_options: str | None) -> str:
    values = [token.strip() for token in (sync_options or "").split(",") if token.strip()]
    if "Delete=false" not in values:
        values.append("Delete=false")
    return ",".join(values)


def apply_inventory_protections(
    path: Path, cluster: dict[str, str], target_pattern: str,
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Record then apply Delete=false for likely pre-existing/ambiguous resources."""
    prior = read_json(path) if path.exists() else {}
    if prior and (
        prior.get("cluster", {}).get("server") != cluster.get("server")
        or prior.get("targetPattern") != target_pattern
    ):
        raise RuntimeError("Inventory protection state belongs to a different cluster or Pattern.")
    known = {
        (item.get("kind"), item.get("namespace"), item.get("name")): item
        for item in prior.get("resources", [])
    }
    state_by_id = dict(known)
    for item in resources:
        if not item.get("uid") or not item.get("apiResource"):
            raise RuntimeError(f"Cannot safely protect {item.get('kind')} {resource_ref(item)} without UID/API identity.")
        identity = (item.get("kind"), item.get("namespace"), item.get("name"))
        saved = known.get(identity)
        if saved:
            if saved.get("uid") != item.get("uid"):
                raise RuntimeError(f"{item.get('kind')} {resource_ref(item)} changed UID since protection was recorded.")
            item["syncOptionsBeforeProtection"] = saved.get("syncOptionsBeforeProtection")
            item["protectionAddedByScript"] = saved.get("protectionAddedByScript", False)
            state_by_id[identity] = saved
            continue

        existing = {
            token.strip()
            for token in (item.get("syncOptions") or "").split(",")
            if token.strip()
        }
        saved = {
            "kind": item.get("kind"),
            "namespace": item.get("namespace"),
            "name": item.get("name"),
            "uid": item.get("uid"),
            "apiResource": item.get("apiResource"),
            "creationTimestamp": item.get("creationTimestamp"),
            "inventoryOwnershipAssessment": item.get("inventoryOwnershipAssessment"),
            "syncOptionsBeforeProtection": item.get("syncOptions"),
            "protectionAddedByScript": "Delete=false" not in existing,
            "trackingIdBeforeProtection": item.get("trackingId"),
            "managedByBeforeProtection": item.get("managedBy"),
            "recordedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        state_by_id[identity] = saved
        item["syncOptionsBeforeProtection"] = saved["syncOptionsBeforeProtection"]
        item["protectionAddedByScript"] = saved["protectionAddedByScript"]

    state = {
        "cluster": cluster,
        "targetPattern": target_pattern,
        "resources": list(state_by_id.values()),
    }
    write_json(path, state)

    for item in resources:
        saved = state_by_id[(item.get("kind"), item.get("namespace"), item.get("name"))]
        if not saved.get("protectionAddedByScript"):
            continue
        expected = append_delete_false(saved.get("syncOptionsBeforeProtection"))
        api_resource = item["apiResource"]
        get_args = ["get", api_resource, item["name"]]
        if item.get("namespace"):
            get_args.extend(["-n", item["namespace"]])
        live = oc_json(get_args)
        metadata = live.get("metadata", {})
        if metadata.get("uid") != item.get("uid"):
            raise RuntimeError(f"{item.get('kind')} {resource_ref(item)} changed UID before protection.")
        annotations = metadata.get("annotations", {}) or {}
        annotation_key = "argocd.argoproj.io/sync-options"
        current_options = annotations.get(annotation_key)
        if current_options == expected:
            item["deleteProtected"] = True
            continue
        if current_options != saved.get("syncOptionsBeforeProtection"):
            raise RuntimeError(
                f"Sync options on {item.get('kind')} {resource_ref(item)} changed since inventory; refusing to overwrite them."
            )
        patch = {"metadata": {"annotations": {annotation_key: expected}}}
        patch_args = ["patch", api_resource, item["name"], "--type=merge", "-p", json.dumps(patch, separators=(",", ":"))]
        if item.get("namespace"):
            patch_args.extend(["-n", item["namespace"]])
        oc(patch_args)
        verified = oc_json(get_args)
        verified_options = ((verified.get("metadata", {}).get("annotations") or {}).get(annotation_key))
        if verified.get("metadata", {}).get("uid") != item.get("uid") or verified_options != expected:
            raise RuntimeError(f"Could not verify Delete=false protection on {item.get('kind')} {resource_ref(item)}.")
        item["deleteProtected"] = True
    print(f"Delete=false protection verified for {len(resources)} likely pre-existing/ambiguous tracked resources.")
    return resources


def release_inventory_protections(
    path: Path, cluster: dict[str, str], target_pattern: str, apps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Release only safeguards this script added; leave unknown prior metadata intact."""
    if not path.exists():
        return []
    state = read_json(path)
    if state.get("cluster", {}).get("server") != cluster.get("server") or state.get("targetPattern") != target_pattern:
        raise RuntimeError("Inventory protection state belongs to a different cluster or Pattern.")
    app_names = {app.get("name") for app in apps if app.get("name")}
    app_keys = {key(app) for app in apps}
    outcomes: list[dict[str, Any]] = []
    for item in state.get("resources", []):
        if not item.get("name") or not item.get("apiResource"):
            outcomes.append({**item, "cleanupState": "unknown", "reason": "missing API resource identity"})
            continue
        args = ["get", item["apiResource"], item["name"]]
        if item.get("namespace"):
            args.extend(["-n", item["namespace"]])
        try:
            live = oc_json(args, allow_missing=True)
        except OcError as error:
            outcomes.append({**item, "cleanupState": "error", "reason": error.stderr})
            continue
        if not live:
            outcomes.append({**item, "cleanupState": "absent"})
            continue
        metadata = live.get("metadata", {})
        if metadata.get("uid") != item.get("uid"):
            outcomes.append({**item, "cleanupState": "conflict", "reason": "live UID differs from inventory UID"})
            continue
        annotations = metadata.get("annotations", {}) or {}
        patch_annotations: dict[str, Any] = {}
        sync_key = "argocd.argoproj.io/sync-options"
        if item.get("protectionAddedByScript"):
            original = item.get("syncOptionsBeforeProtection")
            current = annotations.get(sync_key)
            expected = append_delete_false(original)
            if current == expected:
                patch_annotations[sync_key] = original
            elif current != original:
                outcomes.append({**item, "cleanupState": "conflict", "reason": "sync options changed after protection"})
                continue

        tracking_key = "argocd.argoproj.io/tracking-id"
        current_tracking = annotations.get(tracking_key)
        saved_tracking = item.get("trackingIdBeforeProtection")
        tracking_app = (current_tracking or "").split(":", 1)[0]
        if saved_tracking and current_tracking == saved_tracking and (
            tracking_app in app_names or tracking_app in app_keys
        ):
            patch_annotations[tracking_key] = None

        if patch_annotations:
            patch = {"metadata": {"annotations": patch_annotations}}
            patch_args = ["patch", item["apiResource"], item["name"], "--type=merge", "-p", json.dumps(patch, separators=(",", ":"))]
            if item.get("namespace"):
                patch_args.extend(["-n", item["namespace"]])
            try:
                oc(patch_args)
                outcomes.append({**item, "cleanupState": "released"})
            except OcError as error:
                outcomes.append({**item, "cleanupState": "error", "reason": error.stderr})
        else:
            outcomes.append({**item, "cleanupState": "already-clean"})
    return outcomes


def verify_delete_protection(resources: list[dict[str, Any]]) -> None:
    """Recheck UID and Delete=false immediately before Pattern deletion."""
    for item in resources:
        if not item.get("apiResource") or not item.get("uid"):
            raise RuntimeError(f"Cannot verify deletion protection for {item.get('kind')} {resource_ref(item)}.")
        args = ["get", item["apiResource"], item["name"]]
        if item.get("namespace"):
            args.extend(["-n", item["namespace"]])
        live = oc_json(args)
        metadata = live.get("metadata", {})
        if metadata.get("uid") != item.get("uid"):
            raise RuntimeError(f"{item.get('kind')} {resource_ref(item)} changed UID before Pattern deletion.")
        options = ((metadata.get("annotations") or {}).get("argocd.argoproj.io/sync-options") or "")
        if "Delete=false" not in {token.strip() for token in options.split(",") if token.strip()}:
            raise RuntimeError(
                f"Delete=false protection is missing on {item.get('kind')} {resource_ref(item)}; Pattern deletion was not started."
            )


def do_uninstall(args: argparse.Namespace) -> int:
    require_admin()
    ensure_private_dir(args.artifacts_dir)
    current_cluster = cluster_identity()
    version = operator_version(args.operator_version)
    ensure_operator_version(version)

    current = inventory(workers=args.workers)
    current["inventoryType"] = "current-install-inventory"
    baseline = read_json(args.baseline) if args.baseline else None
    inventory_snapshot = read_json(args.inventory) if args.inventory else None
    comparison_mode = "pre-install-baseline" if baseline is not None else "current-install-inventory"

    if baseline is not None:
        if args.best_effort:
            raise RuntimeError("--best-effort applies only with --inventory; do not use it with --baseline.")
        check_baseline_cluster(baseline, current_cluster)
        pattern_obj = find_pattern(current["resources"]["patterns"], args.pattern, args.namespace)
        pattern_name = pattern_obj["name"]
        namespace = pattern_obj["namespace"]
        is_resume = bool(pattern_obj.get("deletionTimestamp"))
        try:
            root = discover_root(pattern_name, current["resources"]["applications"], args.root_application)
        except RuntimeError:
            if not is_resume:
                raise
            root = args.root_application or f"vp-gitops/{pattern_name}-hub"
        root_exists = root in {key(app) for app in current["resources"]["applications"]}
        selected_apps = app_tree(
            current["resources"]["applications"], root, allow_missing_root=is_resume and not root_exists
        )
    else:
        if not args.best_effort:
            raise RuntimeError("Inventory mode requires the explicit --best-effort option.")
        candidate_pattern = find_pattern(current["resources"]["patterns"], args.pattern, args.namespace)
        is_resume = bool(candidate_pattern.get("deletionTimestamp"))
        pattern_obj, root, selected_apps = validate_current_inventory(
            inventory_snapshot,
            current,
            args.pattern,
            args.namespace,
            args.root_application,
            allow_resume=is_resume,
        )
        pattern_name = pattern_obj["name"]
        namespace = pattern_obj["namespace"]

    pre_uninstall_path = args.artifacts_dir / "pre-uninstall.json"
    if is_resume and pre_uninstall_path.exists():
        report_before = read_json(pre_uninstall_path)
        check_baseline_cluster(report_before, current_cluster)
        saved_pattern = find_pattern(
            report_before.get("resources", {}).get("patterns", []), pattern_name, namespace
        )
        if saved_pattern.get("uid") != pattern_obj.get("uid"):
            raise RuntimeError("The saved pre-uninstall inventory belongs to a different Pattern instance.")
        root = discover_root(
            pattern_name,
            report_before.get("resources", {}).get("applications", []),
            args.root_application,
        )
        saved_apps = app_tree(
            report_before.get("resources", {}).get("applications", []), root
        )
        live_apps = app_tree(
            current.get("resources", {}).get("applications", []),
            root,
            allow_missing_root=True,
        )
        saved_by_key = {key(app): app for app in saved_apps}
        for live_app in live_apps:
            saved_app = saved_by_key.get(key(live_app))
            if not saved_app or not saved_app.get("uid") or saved_app.get("uid") != live_app.get("uid"):
                raise RuntimeError(f"Live Application {key(live_app)} does not match the saved uninstall inventory.")
        if baseline is None:
            validate_current_inventory(
                inventory_snapshot,
                report_before,
                pattern_name,
                namespace,
                root,
                allow_resume=True,
            )
        selected_apps = saved_apps
    else:
        report_before = (
            inventory_snapshot if baseline is None and is_resume else current
        )
        write_inventory_files(args.artifacts_dir, "pre-uninstall", report_before)

    target_pattern = f"{namespace}/{pattern_name}"
    preflight_probe = probe_app_resources(
        selected_apps,
        workers=args.workers,
        removed_crd_kinds=removed_crd_kinds(report_before, current),
    )
    unknown_probes = [
        item for item in preflight_probe
        if item.get("state") == "unknown"
        or (item.get("state") == "present" and (not item.get("uid") or not item.get("apiResource")))
    ]
    if baseline is None and not is_resume:
        verify_tracked_resource_inventory(inventory_snapshot, selected_apps, preflight_probe)
    if baseline is not None:
        baseline_patterns = {key(item) for item in baseline.get("resources", {}).get("patterns", [])}
        baseline_apps = {key(item) for item in baseline.get("resources", {}).get("applications", [])}
        if target_pattern in baseline_patterns or root in baseline_apps:
            raise RuntimeError(
                "The supplied baseline already contains this Pattern/root Application; "
                "use a true pre-install baseline or the explicit --inventory --best-effort workflow."
            )
        preexisting_tracked = find_preexisting_tracked_resources(
            baseline, pattern_obj, selected_apps, preflight_probe
        )
        preexisting_tracked = record_preexisting_resource_state(
            args.artifacts_dir / "preexisting-resource-state.json",
            current_cluster,
            target_pattern,
            preexisting_tracked,
        )
    else:
        if inventory_snapshot.get("scanErrors") and not args.allow_incomplete_inventory:
            raise RuntimeError("The saved current inventory has scan errors; resolve them or explicitly pass --allow-incomplete-inventory.")
        preexisting_tracked = classify_inventory_tracked_resources(pattern_obj, selected_apps, preflight_probe)
        if not is_resume or not report_before.get("trackedResourceInventory"):
            report_before["trackedResourceInventory"] = preflight_probe
            write_inventory_files(args.artifacts_dir, "pre-uninstall", report_before)

    print(f"Cluster: {current_cluster['server']} ({current_cluster['context']})")
    print(f"Inventory mode: {comparison_mode}")
    print(f"Pattern: {target_pattern}")
    print(f"Patterns Operator: {version}")
    print(f"Root Argo Application: {root}")
    print("Argo Application tree:")
    for app in selected_apps:
        print(
            f"  - {key(app)} ({len(app.get('resources', []))} tracked resources; "
            f"automatic sync={'on' if app.get('automatedSync') else 'off'})"
        )
    if preexisting_tracked:
        heading = (
            "Likely pre-existing or ambiguous resources; inventory mode will protect these automatically:"
            if baseline is None
            else "Pre-existing resources currently tracked by this Argo tree:"
        )
        print(heading)
        for item in preexisting_tracked:
            protected = "Delete=false set" if item["deleteProtected"] else "Delete=false missing"
            auto = ", ".join(item["automatedSyncOwners"]) or "automatic sync off"
            print(
                f"  - {item['kind']} {resource_ref(item)} (UID {item['uid']}; "
                f"{item.get('inventoryOwnershipAssessment', 'baseline match')}; {protected}; auto-sync owner: {auto})"
            )
    if unknown_probes:
        print("Argo-tracked resources whose live identity could not be verified:")
        for item in unknown_probes:
            print(f"  - {item.get('kind')} {resource_ref(item)}: {item.get('error', 'unknown error')}")
    tracked_pvcs = sorted(
        {
            resource_ref(item)
            for app in selected_apps
            for item in app.get("resources", [])
            if item.get("kind") == "PersistentVolumeClaim"
        }
    )
    if tracked_pvcs:
        print("Pattern-tracked PVCs (back up or confirm disposable before proceeding):")
        for pvc in tracked_pvcs:
            print(f"  - {pvc}")
    unavailable = [item for item in current["resources"]["managedclusters"] if item.get("available") is False]
    if unavailable:
        print("Unavailable ACM ManagedClusters:")
        for cluster in unavailable:
            print(f"  - {cluster['name']}")
    if current["scanErrors"]:
        print(f"Warning: pre-uninstall inventory has {len(current['scanErrors'])} scan errors.")
    if baseline is None:
        print("No pre-install baseline: trust settings and cluster-wide ownership cannot be compared to their original state.")
    print(f"Artifacts directory: {args.artifacts_dir.resolve()}")
    if not args.execute:
        print("Plan only. No cluster resources were changed. Add --execute and the exact --confirm string to start.")
        print(f"Required confirmation: DELETE {target_pattern} on {current_cluster['server']}")
        return 0

    if not args.expected_server or args.expected_server != current_cluster["server"]:
        raise RuntimeError("--expected-server is required and must exactly match `oc whoami --show-server`.")
    if not args.ack_preflight:
        raise RuntimeError(
            "Before --execute, complete the procedure's backup, enabled-feature, external-integration, and shared-resource review, then pass --ack-preflight."
        )
    unsafe_preexisting = [
        item
        for item in preexisting_tracked
        if baseline is not None and not item["deleteProtected"]
    ]
    if unsafe_preexisting:
        refs = ", ".join(
            f"{item['kind']} {resource_ref(item)}" for item in unsafe_preexisting
        )
        raise RuntimeError(
            "Refusing the Argo cascade because it tracks pre-existing resources without a verified "
            f"Delete=false safeguard: {refs}. Follow the protection steps in "
            "uninstall-procedure.md, then rerun the plan."
        )
    if unknown_probes:
        raise RuntimeError(
            "Refusing the Argo cascade because one or more tracked resources could not be inventoried. "
            "Resolve the listed API or permission errors and rerun the plan."
        )
    if unavailable and not args.allow_unavailable_spokes:
        raise RuntimeError(
            "One or more ACM ManagedClusters are unavailable; resolve connectivity or explicitly pass --allow-unavailable-spokes."
        )
    if current["scanErrors"] and not args.allow_incomplete_inventory:
        raise RuntimeError("Inventory has errors; resolve them or explicitly pass --allow-incomplete-inventory.")
    if baseline is not None and baseline.get("scanErrors") and not args.allow_incomplete_inventory:
        raise RuntimeError("The pre-install baseline has scan errors; resolve them or explicitly pass --allow-incomplete-inventory.")
    require_delete_permission(namespace)
    confirm_execution(args, {"metadata": {"name": pattern_name, "namespace": namespace}}, current_cluster["server"])
    if pattern_obj.get("deletionTimestamp"):
        if baseline is None:
            print(
                "Warning: Pattern deletion already started before this inventory-mode run; "
                "protection cannot recover resources already pruned. Protecting eligible survivors."
            )
            preexisting_tracked = apply_inventory_protections(
                args.artifacts_dir / "inventory-protection-state.json",
                current_cluster,
                target_pattern,
                preexisting_tracked,
            )
        print("Pattern already has a deletion timestamp; resuming progress monitoring.")
    else:
        if baseline is None:
            preexisting_tracked = apply_inventory_protections(
                args.artifacts_dir / "inventory-protection-state.json",
                current_cluster,
                target_pattern,
                preexisting_tracked,
            )
        enable_pattern_pruning(pattern_name, namespace)
        disable_automatic_sync(selected_apps, root)
        if baseline is None:
            preexisting_tracked = apply_inventory_protections(
                args.artifacts_dir / "inventory-protection-state.json",
                current_cluster,
                target_pattern,
                preexisting_tracked,
            )
        verify_delete_protection(preexisting_tracked)
        oc(["delete", PATTERN_RESOURCE, pattern_name, "-n", namespace, "--wait=false"])

    start = time.monotonic()
    progress_path = args.artifacts_dir / "progress.json"
    last_observed: tuple[str, str | None] | None = None
    try:
        while True:
            live = get_pattern(pattern_name, namespace)
            if live is None:
                print("Pattern CR is gone; collecting final inventory.")
                break
            phase, last_error = save_progress(progress_path, live, start)
            observed = (phase, last_error)
            if observed != last_observed:
                print(f"phase={phase}; lastError={last_error or '<none>'}")
                last_observed = observed
            if time.monotonic() - start > args.timeout:
                raise TimeoutError(f"Timed out after {args.timeout}s in phase {phase}: {last_error or 'no operator error reported'}")
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("Interrupted. The Pattern deletion continues in the cluster; rerun this command to resume.", file=sys.stderr)
        return 130
    except TimeoutError as error:
        print(str(error), file=sys.stderr)
        print("No finalizers or remaining resources were force-deleted. Inspect progress.json and operator logs.", file=sys.stderr)
        try:
            save_stalled_diagnostics(args.artifacts_dir, selected_apps, args.workers)
        except Exception as diagnostic_error:
            print(f"Could not capture all stalled diagnostics: {diagnostic_error}", file=sys.stderr)
        return 3

    post = inventory(workers=args.workers)
    write_inventory_files(args.artifacts_dir, "post-uninstall-before-trust-restore", post)
    # Restore only when the Argo Application tree is gone. If any app remains,
    # leave cluster-wide fields untouched and make the residue visible.
    remaining_app_keys = {key(app) for app in post["resources"]["applications"]}
    tree_remaining = [app for app in selected_apps if key(app) in remaining_app_keys]
    trust_actions: list[dict[str, Any]] = []
    preexisting_cleanup: list[dict[str, Any]] = []
    if not tree_remaining:
        if baseline is not None:
            preexisting_cleanup = release_preexisting_resources(preexisting_tracked, selected_apps, baseline)
        else:
            preexisting_cleanup = release_inventory_protections(
                args.artifacts_dir / "inventory-protection-state.json",
                current_cluster,
                target_pattern,
                selected_apps,
            )
        cleanup_by_uid = {item.get("uid"): item for item in preexisting_cleanup}
        for item in preexisting_tracked:
            outcome = cleanup_by_uid.get(item.get("uid"))
            if outcome:
                item["cleanupOutcome"] = outcome.get("cleanupState")
                if outcome.get("reason"):
                    item["cleanupReason"] = outcome["reason"]
        post = inventory(workers=args.workers)
        write_inventory_files(args.artifacts_dir, "post-uninstall-before-trust-restore", post)
        if baseline is not None:
            trust_actions = restore_known_cluster_fields(
                baseline,
                post,
                proxy_configmap=args.proxy_ca_configmap,
                image_configmap=args.image_ca_configmap,
            )
            post = inventory(workers=args.workers)
            trust_actions.extend(
                cleanup_known_trust_configmaps(
                    baseline,
                    post,
                    pattern_obj,
                    proxy_configmap=args.proxy_ca_configmap,
                    image_configmap=args.image_ca_configmap,
                )
            )
        else:
            trust_actions = [{
                "state": "not-restored",
                "reason": "No pre-install baseline; original Proxy/Image trust fields and ConfigMap ownership are unknown.",
            }]
        write_inventory_files(args.artifacts_dir, "post-uninstall", post)
    else:
        trust_actions = [{"state": "not-restored", "reason": "one or more target Argo Applications remain"}]
    probe = probe_app_resources(
        selected_apps,
        workers=args.workers,
        removed_crd_kinds=removed_crd_kinds(report_before, post),
    )

    report = make_report(
        baseline,
        report_before,
        post,
        target_pattern,
        selected_apps,
        probe,
        trust_actions,
        preexisting_tracked,
        preexisting_cleanup,
        comparison_mode=comparison_mode,
    )
    for resource in report["patternManagedResources"]:
        if (
            resource.get("kind") == "Proxy"
            and resource.get("name") == "cluster"
            and report["clusterTrust"]["proxy"]["matchesPreinstall"]
        ):
            resource["state"] = "preserved-platform-object"
            resource["reason"] = "OpenShift Proxy singleton retained; ZTVP trustedCA field matches pre-install inventory"
    write_json(args.artifacts_dir / "report.json", report)
    print(f"Report: {(args.artifacts_dir / 'report.json').resolve()}")
    print(f"Pattern absent: {report['patternAbsent']}")
    print(f"Target Argo Applications remaining: {len(report['targetApplicationsRemaining'])}")
    if baseline is not None:
        print(f"New CRDs remaining since baseline: {len(report['newSincePreinstall']['crds'])}")
        print(f"New APIService objects remaining since baseline: {len(report['newSincePreinstall']['apiservices'])}")
        print(f"New Subscriptions/CSVs remaining since baseline: {len(report['newSincePreinstall']['subscriptions'])}/{len(report['newSincePreinstall']['csvs'])}")
        print(f"New OperatorGroups remaining since baseline: {len(report['newSincePreinstall']['operatorgroups'])}")
        print(f"New namespaces remaining since baseline: {len(report['newSincePreinstall']['namespaces'])}")
        print(f"Custom-resource instances new since baseline: {len(report['newSincePreinstall']['customResourceInstances'])}")
    else:
        print("Pre-install deltas: unavailable; the report contains post-uninstall inventory and tracked-resource results.")
    present = sum(item.get("state") == "present" for item in report["patternManagedResources"])
    unknown = sum(item.get("state") == "unknown" for item in report["patternManagedResources"])
    cleanup_issues = sum(
        item.get("cleanupState") in {"unknown", "error", "conflict"}
        for item in report["preexistingResourceCleanup"]
    )
    print(f"Pattern-tracked resources still present/unreadable: {present}/{unknown}")
    print(f"Retained-resource cleanup issues: {cleanup_issues}")
    print(report["strictZeroResidueNote"])
    if report["targetApplicationsRemaining"] or present or unknown or cleanup_issues:
        print(
            "Uninstall is incomplete. Resolve the listed blockers, then run the finalize command "
            "with this run's pre-uninstall inventory.",
            file=sys.stderr,
        )
        return 3
    return 0


def do_audit(args: argparse.Namespace) -> int:
    require_admin()
    ensure_private_dir(args.artifacts_dir)
    current_cluster = cluster_identity()
    baseline = read_json(args.baseline) if args.baseline else None
    inventory_snapshot = read_json(args.inventory) if args.inventory else None
    if baseline is not None:
        check_baseline_cluster(baseline, current_cluster)
        comparison_mode = "pre-install-baseline"
    else:
        check_baseline_cluster(inventory_snapshot, current_cluster)
        if inventory_snapshot.get("inventoryType") != "current-install-inventory":
            raise RuntimeError("--inventory must reference a file created by the `inventory` command.")
        comparison_mode = "current-install-inventory"
    post = inventory(workers=args.workers)
    write_inventory_files(args.artifacts_dir, "audit-current", post)
    selected_apps: list[dict[str, Any]] = []
    app_probe: list[dict[str, Any]] = []
    target_pattern = args.pattern or "<any-pattern>"
    before = read_json(args.pre_uninstall) if args.pre_uninstall else None
    if comparison_mode == "pre-install-baseline" and before is not None:
        check_baseline_cluster(before, current_cluster)
        name = args.pattern or "layered-zero-trust"
        root = discover_root(name, before.get("resources", {}).get("applications", []), args.root_application)
        selected_apps = app_tree(before.get("resources", {}).get("applications", []), root)
        app_probe = probe_app_resources(
            selected_apps,
            args.workers,
            removed_crd_kinds=removed_crd_kinds(before, post),
        )
    elif comparison_mode == "pre-install-baseline":
        before = baseline
        name = args.pattern or "layered-zero-trust"
        root = args.root_application or f"vp-gitops/{name}-hub"
        live_apps = post.get("resources", {}).get("applications", [])
        selected_apps = app_tree(live_apps, root, allow_missing_root=True)
        app_probe = probe_app_resources(
            selected_apps,
            args.workers,
            removed_crd_kinds=removed_crd_kinds(before, post),
        )
    else:
        before = before or inventory_snapshot
        check_baseline_cluster(before, current_cluster)
        name = args.pattern or "layered-zero-trust"
        validate_current_inventory(
            inventory_snapshot,
            before,
            name,
            args.namespace,
            args.root_application,
            allow_resume=True,
        )
        pattern_records = [
            item for item in before.get("resources", {}).get("patterns", [])
            if item.get("name") == name and (args.namespace is None or item.get("namespace") == args.namespace)
        ]
        if len(pattern_records) != 1:
            raise RuntimeError(f"Expected one Pattern {name!r} in the saved current inventory; found {len(pattern_records)}.")
        pattern_record = pattern_records[0]
        root = discover_root(name, before.get("resources", {}).get("applications", []), args.root_application)
        selected_apps = app_tree(before.get("resources", {}).get("applications", []), root)
        target_pattern = f"{pattern_record['namespace']}/{name}"
        app_probe = probe_app_resources(
            selected_apps,
            args.workers,
            removed_crd_kinds=removed_crd_kinds(before, post),
        )
    preexisting_tracked: list[dict[str, Any]] = []
    if comparison_mode == "pre-install-baseline":
        pattern_record = next(
            (
                item
                for item in before.get("resources", {}).get("patterns", [])
                if item.get("name") == (args.pattern or "layered-zero-trust")
                and (args.namespace is None or item.get("namespace") == args.namespace)
            ),
            None,
        )
        if pattern_record:
            preexisting_tracked = find_preexisting_tracked_resources(
                baseline, pattern_record, selected_apps, app_probe
            )
    else:
        state_path = args.artifacts_dir / "inventory-protection-state.json"
        if state_path.exists():
            protection_state = read_json(state_path)
            if (
                protection_state.get("cluster", {}).get("server") != current_cluster.get("server")
                or protection_state.get("targetPattern") != target_pattern
            ):
                raise RuntimeError("Inventory protection state belongs to a different cluster or Pattern.")
            preexisting_tracked = protection_state.get("resources", [])
        else:
            app_keys = {key(app) for app in selected_apps}
            saved_probe = [
                item for item in before.get("trackedResourceInventory", []) or []
                if set(item.get("trackedByApps", [])) & app_keys
            ]
            if any("protectFromCascade" in item for item in saved_probe):
                preexisting_tracked = [item for item in saved_probe if item.get("protectFromCascade")]
            else:
                preexisting_tracked = classify_inventory_tracked_resources(
                    pattern_record, selected_apps, saved_probe or app_probe
                )
    report = make_report(
        baseline,
        before,
        post,
        target_pattern,
        selected_apps,
        app_probe,
        [],
        preexisting_tracked,
        comparison_mode=comparison_mode,
    )
    report["patternAbsent"] = not any(
        (args.pattern is None or item.get("name") == args.pattern)
        and (args.namespace is None or item.get("namespace") == args.namespace)
        for item in post["resources"].get("patterns", [])
    )
    write_json(args.artifacts_dir / "report.json", report)
    print(f"Audit report: {(args.artifacts_dir / 'report.json').resolve()}")
    print(f"Pre-existing Argo-tracked resources: {len(report['preexistingTrackedResources'])}")
    if comparison_mode == "pre-install-baseline":
        print(f"New CRDs: {len(report['newSincePreinstall']['crds'])}")
        print(f"New APIServices: {len(report['newSincePreinstall']['apiservices'])}")
        print(f"New custom-resource instances: {len(report['newSincePreinstall']['customResourceInstances'])}")
    else:
        print("Pre-install deltas are unavailable; compare saved inventory and post-uninstall inventory manually.")
    print(report["strictZeroResidueNote"])
    return 0


def readiness_condition(obj: dict[str, Any] | None, condition_type: str = "Ready") -> dict[str, Any] | None:
    if not obj:
        return None
    for condition in (obj.get("status", {}).get("conditions", []) or []):
        if condition.get("type") == condition_type:
            return condition
    return None


def inspect_reinstall_health(
    *,
    vault_namespace: str,
    app_namespace: str,
    external_secrets: list[str],
    applications: list[str],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    pod = oc_json(["get", "pod", "vault-0", "-n", vault_namespace], allow_missing=True)
    pod_conditions = (pod or {}).get("status", {}).get("conditions", []) or []
    pod_ready = any(item.get("type") == "Ready" and item.get("status") == "True" for item in pod_conditions)
    checks.append(
        {
            "name": f"pod/{vault_namespace}/vault-0",
            "ok": pod_ready,
            "phase": (pod or {}).get("status", {}).get("phase", "Missing"),
            "ready": pod_ready,
            "uid": (pod or {}).get("metadata", {}).get("uid"),
        }
    )

    store = oc_json(["get", "clustersecretstore", "vault-backend"], allow_missing=True)
    store_condition = readiness_condition(store)
    checks.append(
        {
            "name": "clustersecretstore/vault-backend",
            "ok": bool(store_condition and store_condition.get("status") == "True"),
            "status": store_condition.get("status") if store_condition else "Missing",
            "reason": store_condition.get("reason") if store_condition else None,
            "message": store_condition.get("message") if store_condition else None,
        }
    )

    for namespace, name in external_secrets:
        external_secret = oc_json(
            ["get", "externalsecret", name, "-n", namespace],
            allow_missing=True,
        )
        condition = readiness_condition(external_secret)
        remote_paths = [
            entry.get("remoteRef", {}).get("key")
            for entry in (external_secret or {}).get("spec", {}).get("data", []) or []
            if entry.get("remoteRef", {}).get("key")
        ]
        checks.append(
            {
                "name": f"externalsecret/{namespace}/{name}",
                "ok": bool(condition and condition.get("status") == "True"),
                "status": condition.get("status") if condition else "Missing",
                "reason": condition.get("reason") if condition else None,
                "message": condition.get("message") if condition else None,
                "vaultPaths": remote_paths,
            }
        )

    for name in applications:
        application = oc_json(["get", "applications.argoproj.io", name, "-n", app_namespace], allow_missing=True)
        status = (application or {}).get("status", {})
        sync_status = status.get("sync", {}).get("status", "Missing")
        health_status = status.get("health", {}).get("status", "Missing")
        operation_state = status.get("operationState", {}) or {}
        checks.append(
            {
                "name": f"application/{app_namespace}/{name}",
                "ok": sync_status == "Synced" and health_status == "Healthy",
                "sync": sync_status,
                "health": health_status,
                "lastOperation": operation_state.get("phase"),
                "conditions": [
                    {"type": item.get("type"), "message": item.get("message")}
                    for item in status.get("conditions", []) or []
                ],
            }
        )

    return checks


def do_verify_reinstall(args: argparse.Namespace) -> int:
    current_cluster = cluster_identity()
    if args.expected_server and current_cluster.get("server") != args.expected_server:
        raise RuntimeError(
            f"Connected to {current_cluster.get('server')!r}, expected {args.expected_server!r}."
        )

    external_secrets = args.external_secret or [
        ("qtodo-db", "qtodo-db-secret"),
        ("qtodo", "qtodo-truststore-secret"),
    ]
    applications = args.application or ["qtodo", "qtodo-db"]
    started = time.monotonic()
    while True:
        checks = inspect_reinstall_health(
            vault_namespace=args.vault_namespace,
            app_namespace=args.app_namespace,
            external_secrets=external_secrets,
            applications=applications,
        )
        if all(item["ok"] for item in checks) or time.monotonic() - started >= args.wait_seconds:
            break
        time.sleep(min(args.poll_interval, max(0.0, args.wait_seconds - (time.monotonic() - started))))

    passed = all(item["ok"] for item in checks)
    report = {
        "checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cluster": current_cluster,
        "status": "PASS" if passed else "FAIL",
        "elapsedSeconds": round(time.monotonic() - started, 1),
        "checks": checks,
        "note": (
            "Read-only check. A Valid ClusterSecretStore does not prove every Vault path is readable. "
            "For SecretSyncedError, use the listed Vault path and External Secrets controller logs to diagnose policy access."
        ),
    }
    write_json(args.output, report)
    print(f"Reinstall check: {report['status']} ({report['elapsedSeconds']}s)")
    print(f"Report: {args.output.resolve()}")
    for item in checks:
        state = "PASS" if item["ok"] else "FAIL"
        detail = ", ".join(
            f"{key}={value}"
            for key, value in item.items()
            if key not in {"name", "ok", "vaultPaths", "conditions"} and value is not None
        )
        if item.get("vaultPaths"):
            detail += (", " if detail else "") + "vaultPaths=" + ",".join(item["vaultPaths"])
        print(f"{state} {item['name']}: {detail or 'ready'}")
    return 0 if passed else 3


def do_finalize(args: argparse.Namespace) -> int:
    """Finish retained-resource cleanup after an administrator resolves blockers.

    The Pattern Operator can remove its Pattern object before Argo CD finishes
    deleting the root Application. This command uses the saved pre-uninstall
    tree to resume only the safe post-cascade work; it never clears finalizers
    or deletes remaining Applications.
    """
    require_admin()
    ensure_private_dir(args.artifacts_dir)
    current_cluster = cluster_identity()
    baseline = read_json(args.baseline) if args.baseline else None
    inventory_snapshot = read_json(args.inventory) if args.inventory else None
    before = read_json(args.pre_uninstall) if args.pre_uninstall else inventory_snapshot
    if baseline is not None:
        check_baseline_cluster(baseline, current_cluster)
        comparison_mode = "pre-install-baseline"
    else:
        check_baseline_cluster(inventory_snapshot, current_cluster)
        check_baseline_cluster(before, current_cluster)
        if inventory_snapshot.get("inventoryType") != "current-install-inventory":
            raise RuntimeError("--inventory must reference a file created by the `inventory` command.")
        _, _, _ = validate_current_inventory(
            inventory_snapshot,
            before,
            args.pattern or "layered-zero-trust",
            args.namespace,
            args.root_application,
            allow_resume=True,
        )
        comparison_mode = "current-install-inventory"
    check_baseline_cluster(before, current_cluster)

    pattern_name = args.pattern or "layered-zero-trust"
    candidates = [
        item
        for item in before.get("resources", {}).get("patterns", [])
        if item.get("name") == pattern_name
        and (args.namespace is None or item.get("namespace") == args.namespace)
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one pre-uninstall record for Pattern {pattern_name!r}; found {len(candidates)}."
        )
    pattern_record = candidates[0]
    target_pattern = f"{pattern_record['namespace']}/{pattern_name}"
    root = discover_root(
        pattern_name,
        before.get("resources", {}).get("applications", []),
        args.root_application,
    )
    selected_apps = app_tree(before.get("resources", {}).get("applications", []), root)
    current = inventory(workers=args.workers)
    write_inventory_files(args.artifacts_dir, "finalize-before", current)

    pattern_still_exists = any(
        key(item) == target_pattern for item in current.get("resources", {}).get("patterns", [])
    )
    live_app_keys = {key(item) for item in current.get("resources", {}).get("applications", [])}
    remaining_apps = [app for app in selected_apps if key(app) in live_app_keys]
    probe = probe_app_resources(
        selected_apps,
        workers=args.workers,
        removed_crd_kinds=removed_crd_kinds(before, current),
    )
    if baseline is not None:
        preexisting_tracked = find_preexisting_tracked_resources(
            baseline, pattern_record, selected_apps, probe
        )
    else:
        state_path = args.preexisting_state or args.artifacts_dir / "inventory-protection-state.json"
        if state_path.exists():
            state = read_json(state_path)
            if state.get("cluster", {}).get("server") != current_cluster.get("server"):
                raise RuntimeError("Inventory protection state belongs to a different cluster.")
            preexisting_tracked = state.get("resources", [])
        else:
            app_keys = {key(app) for app in selected_apps}
            saved_probe = [
                item for item in before.get("trackedResourceInventory", []) or []
                if set(item.get("trackedByApps", [])) & app_keys
            ]
            if any("protectFromCascade" in item for item in saved_probe):
                preexisting_tracked = [item for item in saved_probe if item.get("protectFromCascade")]
            else:
                preexisting_tracked = classify_inventory_tracked_resources(
                    pattern_record, selected_apps, saved_probe or probe
                )

    if pattern_still_exists or remaining_apps:
        report = make_report(
            baseline,
            before,
            current,
            target_pattern,
            selected_apps,
            probe,
            [],
            preexisting_tracked,
            comparison_mode=comparison_mode,
        )
        write_json(args.artifacts_dir / "report.json", report)
        print(f"Pattern absent: {report['patternAbsent']}")
        print(f"Target Argo Applications remaining: {len(report['targetApplicationsRemaining'])}")
        print("Post-deletion finalization was not run; finish the Pattern or Argo deletion first.", file=sys.stderr)
        return 3

    if baseline is not None:
        state_path = args.preexisting_state or args.artifacts_dir / "preexisting-resource-state.json"
        preexisting_tracked = record_preexisting_resource_state(
            state_path,
            current_cluster,
            target_pattern,
            preexisting_tracked,
        )
        preexisting_cleanup = release_preexisting_resources(preexisting_tracked, selected_apps, baseline)
    else:
        state_path = args.preexisting_state or args.artifacts_dir / "inventory-protection-state.json"
        preexisting_cleanup = release_inventory_protections(
            state_path,
            current_cluster,
            target_pattern,
            selected_apps,
        )
    cleanup_by_uid = {item.get("uid"): item for item in preexisting_cleanup}
    for item in preexisting_tracked:
        outcome = cleanup_by_uid.get(item.get("uid"))
        if outcome:
            item["cleanupOutcome"] = outcome.get("cleanupState")
            if outcome.get("reason"):
                item["cleanupReason"] = outcome["reason"]

    post = inventory(workers=args.workers)
    write_inventory_files(args.artifacts_dir, "post-uninstall-before-trust-restore", post)
    if baseline is not None:
        trust_actions = restore_known_cluster_fields(
            baseline,
            post,
            proxy_configmap=args.proxy_ca_configmap,
            image_configmap=args.image_ca_configmap,
        )
        post = inventory(workers=args.workers)
        trust_actions.extend(
            cleanup_known_trust_configmaps(
                baseline,
                post,
                pattern_record,
                proxy_configmap=args.proxy_ca_configmap,
                image_configmap=args.image_ca_configmap,
            )
        )
    else:
        trust_actions = [{
            "state": "not-restored",
            "reason": "No pre-install baseline; original Proxy/Image trust fields and ConfigMap ownership are unknown.",
        }]
    post = inventory(workers=args.workers)
    write_inventory_files(args.artifacts_dir, "post-uninstall", post)
    probe = probe_app_resources(
        selected_apps,
        workers=args.workers,
        removed_crd_kinds=removed_crd_kinds(before, post),
    )
    report = make_report(
        baseline,
        before,
        post,
        target_pattern,
        selected_apps,
        probe,
        trust_actions,
        preexisting_tracked,
        preexisting_cleanup,
        comparison_mode=comparison_mode,
    )
    for resource in report["patternManagedResources"]:
        if (
            resource.get("kind") == "Proxy"
            and resource.get("name") == "cluster"
            and report["clusterTrust"]["proxy"]["matchesPreinstall"]
        ):
            resource["state"] = "preserved-platform-object"
            resource["reason"] = "OpenShift Proxy singleton retained; ZTVP trustedCA field matches pre-install inventory"
    write_json(args.artifacts_dir / "report.json", report)

    print(f"Report: {(args.artifacts_dir / 'report.json').resolve()}")
    print(f"Pattern absent: {report['patternAbsent']}")
    print(f"Target Argo Applications remaining: {len(report['targetApplicationsRemaining'])}")
    print(f"Pre-existing resources released: {sum(item.get('cleanupState') == 'released' for item in preexisting_cleanup)}")
    if baseline is not None:
        print(f"Proxy trust matches pre-install: {report['clusterTrust']['proxy']['matchesPreinstall']}")
        print(f"Image trust matches pre-install: {report['clusterTrust']['image']['matchesPreinstall']}")
    else:
        print("Proxy/Image trust restoration: unavailable without a pre-install baseline; original values were not changed.")
    present = sum(item.get("state") == "present" for item in report["patternManagedResources"])
    unknown = sum(item.get("state") == "unknown" for item in report["patternManagedResources"])
    cleanup_issues = sum(
        item.get("cleanupState") in {"unknown", "error", "conflict"}
        for item in report["preexistingResourceCleanup"]
    )
    print(f"Pattern-tracked resources still present/unreadable: {present}/{unknown}")
    print(f"Retained-resource cleanup issues: {cleanup_issues}")
    print(report["strictZeroResidueNote"])
    if (
        report["targetApplicationsRemaining"]
        or present
        or unknown
        or (baseline is not None and not all(value["matchesPreinstall"] for value in report["clusterTrust"].values()))
        or cleanup_issues
        or report["scanErrors"]
    ):
        return 3
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventory, uninstall, and audit a ZTVP installation using oc.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    snapshot = subparsers.add_parser("snapshot", help="capture the cluster baseline before ZTVP installation")
    snapshot.add_argument("--output", type=Path, default=Path("ztvp-preinstall-baseline.json"))
    snapshot.add_argument("--overwrite", action="store_true")
    snapshot.add_argument("--workers", type=int, default=4)
    snapshot.set_defaults(func=do_snapshot)

    current_inventory = subparsers.add_parser(
        "inventory", help="capture the current state of an already-installed Pattern"
    )
    current_inventory.add_argument("--output", type=Path, default=Path("ztvp-current-inventory.json"))
    current_inventory.add_argument("--overwrite", action="store_true")
    current_inventory.add_argument("--workers", type=int, default=4)
    current_inventory.set_defaults(func=do_inventory)

    uninstall = subparsers.add_parser("uninstall", help="plan or execute phased Pattern deletion and audit")
    source = uninstall.add_mutually_exclusive_group(required=True)
    source.add_argument("--baseline", type=Path, help="JSON created by snapshot before ZTVP install")
    source.add_argument("--inventory", type=Path, help="current-install inventory captured before uninstall")
    uninstall.add_argument(
        "--best-effort", action="store_true",
        help="explicitly accept heuristic ownership decisions when using --inventory without a pre-install baseline",
    )
    uninstall.add_argument("--pattern", help="Pattern CR name; required if more than one exists")
    uninstall.add_argument("--namespace", help="Pattern CR namespace")
    uninstall.add_argument("--root-application", help="Argo root Application as namespace/name")
    uninstall.add_argument("--operator-version", help="explicit version when it cannot be discovered automatically")
    uninstall.add_argument("--proxy-ca-configmap", default=KNOWN_ZTVP_TRUST_CONFIGMAPS["proxy"])
    uninstall.add_argument("--image-ca-configmap", default=KNOWN_ZTVP_TRUST_CONFIGMAPS["image"])
    uninstall.add_argument("--artifacts-dir", type=Path, default=Path("ztvp-uninstall-artifacts"))
    uninstall.add_argument("--execute", action="store_true", help="delete the Pattern CR after all preflight checks")
    uninstall.add_argument(
        "--ack-preflight",
        action="store_true",
        help="confirm backups, feature/external integration inventory, spoke reachability, and shared-resource review",
    )
    uninstall.add_argument("--allow-unavailable-spokes", action="store_true", help="proceed despite unavailable ACM ManagedClusters; residue may remain")
    uninstall.add_argument("--expected-server", help="required with --execute; exact output of oc whoami --show-server")
    uninstall.add_argument("--confirm", help="exact confirmation string printed by the plan")
    uninstall.add_argument("--allow-incomplete-inventory", action="store_true")
    uninstall.add_argument("--timeout", type=int, default=4 * 60 * 60, help="phase monitoring timeout in seconds")
    uninstall.add_argument("--poll-interval", type=int, default=15)
    uninstall.add_argument("--workers", type=int, default=4)
    uninstall.set_defaults(func=do_uninstall)

    audit = subparsers.add_parser("audit", help="compare the cluster with a baseline or current-install inventory")
    audit_source = audit.add_mutually_exclusive_group(required=True)
    audit_source.add_argument("--baseline", type=Path)
    audit_source.add_argument("--inventory", type=Path, help="current-install inventory captured before uninstall")
    audit.add_argument("--pattern", default="layered-zero-trust")
    audit.add_argument("--namespace")
    audit.add_argument("--root-application", help="root Application as namespace/name; used with --pre-uninstall")
    audit.add_argument("--pre-uninstall", type=Path, help="pre-uninstall.json from an earlier run, for app-resource checks")
    audit.add_argument("--artifacts-dir", type=Path, default=Path("ztvp-uninstall-audit"))
    audit.add_argument("--workers", type=int, default=4)
    audit.set_defaults(func=do_audit)

    reinstall_check = subparsers.add_parser(
        "verify-reinstall",
        help="read-only smoke check for Vault, qtodo ExternalSecrets, and Argo health after reinstall",
    )
    reinstall_check.add_argument("--expected-server", help="fail if oc is connected to a different API server")
    reinstall_check.add_argument("--vault-namespace", default="vault")
    reinstall_check.add_argument("--app-namespace", default="vp-gitops")
    reinstall_check.add_argument(
        "--external-secret",
        action="append",
        metavar="NAMESPACE/NAME",
        help="ExternalSecret to check; defaults to qtodo database and truststore secrets",
    )
    reinstall_check.add_argument(
        "--application",
        action="append",
        help="Argo Application to check; defaults to qtodo and qtodo-db",
    )
    reinstall_check.add_argument("--wait-seconds", type=int, default=0, help="poll until ready or this timeout")
    reinstall_check.add_argument("--poll-interval", type=int, default=15)
    reinstall_check.add_argument(
        "--output", type=Path, default=Path("ztvp-uninstall-artifacts/reinstall-check.json")
    )
    reinstall_check.set_defaults(func=do_verify_reinstall)

    finalize = subparsers.add_parser(
        "finalize",
        help="release recorded safeguards and audit after Pattern and Argo deletion finish",
    )
    finalize_source = finalize.add_mutually_exclusive_group(required=True)
    finalize_source.add_argument("--baseline", type=Path)
    finalize_source.add_argument("--inventory", type=Path, help="current-install inventory captured before uninstall")
    finalize.add_argument("--pre-uninstall", type=Path, required=True, help="pre-uninstall.json from the uninstall run")
    finalize.add_argument("--pattern", default="layered-zero-trust")
    finalize.add_argument("--namespace")
    finalize.add_argument("--root-application", help="root Application as namespace/name")
    finalize.add_argument("--preexisting-state", type=Path, help="saved retention state; defaults under --artifacts-dir")
    finalize.add_argument("--proxy-ca-configmap", default=KNOWN_ZTVP_TRUST_CONFIGMAPS["proxy"])
    finalize.add_argument("--image-ca-configmap", default=KNOWN_ZTVP_TRUST_CONFIGMAPS["image"])
    finalize.add_argument("--artifacts-dir", type=Path, default=Path("ztvp-uninstall-artifacts"))
    finalize.add_argument("--workers", type=int, default=4)
    finalize.set_defaults(func=do_finalize)
    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    if not shutil.which("oc"):
        print("oc CLI is required and must be on PATH.", file=sys.stderr)
        return 2
    for name in ("external_secret", "application"):
        values = getattr(args, name, None)
        if values is not None:
            parsed: list[Any] = []
            for value in values:
                if name == "external_secret":
                    namespace, separator, resource_name = value.partition("/")
                    if not separator or not namespace or not resource_name:
                        parser.error("--external-secret must use NAMESPACE/NAME")
                    parsed.append((namespace, resource_name))
                else:
                    parsed.append(value)
            setattr(args, name, parsed)
    if (
        (hasattr(args, "workers") and args.workers < 1)
        or (hasattr(args, "poll_interval") and args.poll_interval < 1)
        or (hasattr(args, "timeout") and args.timeout < 1)
        or (hasattr(args, "wait_seconds") and args.wait_seconds < 0)
    ):
        parser.error("--workers, --poll-interval, and --timeout must be positive; --wait-seconds must be non-negative")
    try:
        return args.func(args)
    except (OcError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
