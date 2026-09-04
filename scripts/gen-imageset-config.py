#!/usr/bin/env python3
"""Generate an ImageSetConfiguration for oc mirror v2 from a running ZTVP cluster.

Detects OCP version, installed operator subscriptions, catalog sources, and
workload images by querying the live cluster via oc CLI.

Usage:
  python3 scripts/gen-imageset-config.py [--prefix PREFIX]

  Writes three ImageSetConfiguration files:
    releases-imageset-config.yaml   - OCP release images
    operators-imageset-config.yaml  - operator catalogs
    images-imageset-config.yaml     - Helm charts and workload images

  Optional --prefix prepends each filename (e.g. /tmp/ztvp-offline/clustername)

Requirements:
  - oc (OpenShift CLI)
  - access to the target cluster
  - the ZTVP pattern installed on the cluster
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import IO, Optional

VP_OCI_REGISTRY = "quay.io/validatedpatterns"
VP_CHARTS_REPO = "charts.validatedpatterns.io"


@dataclass
class OperatorSpec:
    """Describes an operator the pattern can deploy (mandatory or optional)."""

    name: str  # OLM package name
    channel: str  # target channel; may contain {ocp_minor} placeholder
    catalog_source: str  # CatalogSource name in openshift-marketplace
    ocp_versioned_channel: bool = False  # expand {ocp_minor} in channel at runtime
    optional: bool = False  # True: disabled by default in values-hub.yaml

    def resolved_channel(self, ocp_minor: str) -> str:
        """Return the channel with {ocp_minor} expanded when applicable."""
        if self.ocp_versioned_channel:
            return self.channel.format(ocp_minor=ocp_minor)
        return self.channel


# Complete list of operators the pattern supports — mandatory and optional.
# Optional operators (commented out in values-hub.yaml) are still included so
# the mirror registry is ready for any feature combination without re-mirroring.
# For installed operators the script overrides channel and version with live
# cluster data. For uninstalled operators it falls back to PackageManifest.
OPERATORS: list = [
    # Core framework
    OperatorSpec("openshift-gitops-operator", "gitops-1.21", "redhat-operators"),
    OperatorSpec("patterns-operator", "fast", "community-operators"),
    # Cluster management
    OperatorSpec("advanced-cluster-management", "release-2.16", "redhat-operators"),
    OperatorSpec("multicluster-engine", "stable-2.11", "redhat-operators"),
    # Security
    OperatorSpec("rhacs-operator", "stable", "redhat-operators"),
    OperatorSpec("compliance-operator", "stable", "redhat-operators"),
    # Identity and secrets
    OperatorSpec("openshift-cert-manager-operator", "stable-v1", "redhat-operators"),
    OperatorSpec("rhbk-operator", "stable-v26.4", "redhat-operators"),
    OperatorSpec(
        "openshift-external-secrets-operator", "stable-v1", "redhat-operators"
    ),
    OperatorSpec(
        "openshift-zero-trust-workload-identity-manager",
        "stable-v1",
        "redhat-operators",
    ),
    # Optional — storage (channel name includes OCP minor version)
    OperatorSpec(
        "odf-operator",
        "stable-{ocp_minor}",
        "redhat-operators",
        ocp_versioned_channel=True,
        optional=True,
    ),
    OperatorSpec(
        "lvms-operator",
        "stable-{ocp_minor}",
        "redhat-operators",
        ocp_versioned_channel=True,
        optional=True,
    ),
    # Optional — observability
    OperatorSpec("loki-operator", "stable-6.6", "redhat-operators", optional=True),
    OperatorSpec("netobserv-operator", "stable", "redhat-operators", optional=True),
    # Optional — secure supply chain
    OperatorSpec(
        "openshift-pipelines-operator-rh", "latest", "redhat-operators", optional=True
    ),
    OperatorSpec("rhtas-operator", "stable", "redhat-operators", optional=True),
    OperatorSpec("rhtpa-operator", "stable-v1.1", "redhat-operators", optional=True),
    # Optional — registry
    OperatorSpec("quay-operator", "stable-3.17", "redhat-operators", optional=True),
]


def oc(*args: str) -> Optional[dict]:
    """Run an oc command and return parsed JSON output, or None on failure."""
    cmd = ["oc"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Warning: {' '.join(cmd)}: {result.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(result.stdout) if result.stdout.strip() else None


def get_ocp_version() -> tuple:
    """Return (full_version, minor_version) e.g. ('4.22.7', '4.22')."""
    data = oc("get", "clusterversion", "version", "-o", "json")
    if not data:
        sys.exit("Error: cannot read cluster version. Are you logged in?")
    full = data["status"]["desired"]["version"]
    minor = ".".join(full.split(".")[:2])
    return full, minor


def get_catalog_image(source_name: str) -> str:
    """Return the image URL for a CatalogSource in openshift-marketplace."""
    data = oc(
        "get",
        "catalogsource",
        source_name,
        "-n",
        "openshift-marketplace",
        "-o",
        "json",
    )
    if data:
        return data.get("spec", {}).get("image", "")
    return ""


def get_subscriptions() -> dict:
    """Return dict: package_name -> subscription info."""
    data = oc("get", "subscriptions.operators.coreos.com", "-A", "-o", "json")
    if not data:
        return {}
    subs = {}
    for item in data.get("items", []):
        spec = item.get("spec", {})
        status = item.get("status", {})
        pkg = spec.get("name", "")
        if pkg:
            subs[pkg] = {
                "channel": spec.get("channel", ""),
                "catalogSource": spec.get("source", ""),
                "installedCSV": status.get("installedCSV", ""),
                "currentCSV": status.get("currentCSV", ""),
            }
    return subs


def csv_version(csv_name: str) -> str:
    """Extract version from a CSV name: 'pkg.v1.2.3' -> '1.2.3'."""
    if csv_name and ".v" in csv_name:
        return csv_name.split(".v", 1)[-1]
    return ""


def get_workload_namespaces() -> set:
    """
    Return namespaces managed by the ZTVP ArgoCD instance.

    Namespaces with the argocd.argoproj.io/managed-by label are ZTVP workload
    namespaces.  The label value is the ArgoCD instance namespace itself
    (e.g. layered-zero-trust-hub), which we exclude since it contains ArgoCD
    infrastructure images already covered by the GitOps operator catalog.
    """
    # Always include these regardless of ArgoCD labels
    extras = {"openshift-config"}

    data = oc("get", "namespaces", "-o", "json")
    if not data:
        return extras

    argocd_instance_namespaces = set()
    managed_namespaces = set()

    for item in data.get("items", []):
        labels = item.get("metadata", {}).get("labels", {})
        managed_by = labels.get("argocd.argoproj.io/managed-by", "")
        name = item["metadata"]["name"]
        if managed_by:
            argocd_instance_namespaces.add(managed_by)
            managed_namespaces.add(name)

    return (managed_namespaces - argocd_instance_namespaces) | extras


def collect_images(namespaces: set) -> dict:
    """
    Return dict: image_ref -> (namespace, workload_name).

    Uses the image reference from the pod/CronJob spec — the rendered Helm chart
    value — so tag-based references in charts are preserved as tags in the output.
    Images pinned to a digest in the chart spec are kept as digests.
    Also scans CronJob specs for images that may not have running pods.
    """
    images: dict = {}

    data = oc("get", "pods", "-A", "-o", "json")
    if data:
        for pod in data.get("items", []):
            ns = pod["metadata"]["namespace"]
            if ns not in namespaces:
                continue
            pod_name = pod["metadata"]["name"]

            all_containers = pod.get("spec", {}).get("containers", []) + pod.get(
                "spec", {}
            ).get("initContainers", [])
            for c in all_containers:
                img = c["image"]
                if img not in images:
                    images[img] = (ns, pod_name)

    # CronJobs may have no running pods; read the image from the spec directly
    data = oc("get", "cronjobs", "-A", "-o", "json")
    if data:
        for cj in data.get("items", []):
            ns = cj["metadata"]["namespace"]
            if ns not in namespaces:
                continue
            name = cj["metadata"]["name"]
            containers = (
                cj.get("spec", {})
                .get("jobTemplate", {})
                .get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers", [])
            )
            for c in containers:
                img = c["image"]
                if img not in images:
                    images[img] = (ns, name)

    return images


def get_package_manifests() -> dict:
    """
    Return dict: package_name -> {defaultChannel, channels: {name: version}}.
    Fetched in bulk from openshift-marketplace to avoid per-operator oc calls.
    """
    data = oc("get", "packagemanifest", "-n", "openshift-marketplace", "-o", "json")
    if not data:
        return {}
    result = {}
    for item in data.get("items", []):
        name = item["metadata"]["name"]
        status = item.get("status", {})
        channels = {
            ch["name"]: ch.get("currentCSVDesc", {}).get("version", "")
            for ch in status.get("channels", [])
            if ch.get("name")
        }
        result[name] = {
            "defaultChannel": status.get("defaultChannel", ""),
            "channels": channels,
        }
    return result


def build_catalog_groups(
    operators: list,
    subscriptions: dict,
    package_manifests: dict,
    catalog_images: dict,
    ocp_minor: str,
) -> dict:
    """
    Build catalog_image -> [operator dicts] from the OPERATORS static list.

    For each OperatorSpec:
    - Installed (Subscription found): use cluster channel + installed CSV version.
    - Not installed (optional/auto-managed): use spec channel + PackageManifest version.
    - defaultChannel is added when the target channel differs from the catalog default,
      so oc mirror mirrors the pinned channel rather than the catalog's current one.
    """
    by_catalog: dict = defaultdict(list)

    for spec in operators:
        target_channel = spec.resolved_channel(ocp_minor)
        sub = subscriptions.get(spec.name)
        pm = package_manifests.get(spec.name, {})

        # For installed operators prefer the subscription's actual catalog source so
        # we don't miss operators when catalog_source in OPERATORS differs from cluster.
        effective_source = (
            sub["catalogSource"]
            if sub and sub.get("catalogSource")
            else spec.catalog_source
        )
        catalog_image = catalog_images.get(effective_source, "")
        if not catalog_image:
            # Fall back to spec catalog source in case sub's source is also missing
            catalog_image = catalog_images.get(spec.catalog_source, "")
        if not catalog_image:
            print(
                f"  Warning: CatalogSource '{effective_source}' not resolved "
                f"({spec.name}) - skipping",
                file=sys.stderr,
            )
            continue

        if sub:
            channel = sub["channel"]
            version = csv_version(sub["installedCSV"]) or csv_version(sub["currentCSV"])
        else:
            channel = target_channel
            version = pm.get("channels", {}).get(channel, "")

        op: dict = {"name": spec.name, "channel": channel, "version": version}
        pm_default = pm.get("defaultChannel", "")
        if channel and pm_default and channel != pm_default:
            op["defaultChannel"] = channel

        by_catalog[catalog_image].append(op)

    return dict(by_catalog)


def get_helm_chart_sources() -> list:
    """
    Return list of (chart_name, version_constraint) from ArgoCD Application sources
    pointing to charts.validatedpatterns.io, plus fixed extras not in any Application.
    """
    data = oc("get", "applications.argoproj.io", "-A", "-o", "json")
    charts: dict = {}
    if data:
        for app in data.get("items", []):
            for source in app.get("spec", {}).get("sources", []):
                repo_url = source.get("repoURL", "")
                chart = source.get("chart", "")
                constraint = source.get("targetRevision", "")
                if VP_CHARTS_REPO in repo_url and chart:
                    charts[chart] = constraint

    # OCI subchart dependency declared in charts/rh-keycloak/Chart.yaml (>=0.1.0)
    charts.setdefault("rhbk", "")
    # Bootstrap chart used by pattern.sh - not an ArgoCD Application
    charts.setdefault("pattern-install", "")

    return list(charts.items())


def skopeo_list_tags(image: str) -> list:
    """Return all tags for an OCI image via skopeo, or [] on failure."""
    result = subprocess.run(
        ["skopeo", "list-tags", f"docker://{image}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"  Warning: skopeo list-tags {image}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    return json.loads(result.stdout).get("Tags", [])


def _version_key(v: str) -> tuple:
    """Parse a dotted version string into a sortable int tuple."""
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def latest_matching_tag(tags: list, constraint: str) -> str:
    """
    Return the highest version tag from tags that satisfies constraint.

    Constraint formats:
      '0.9.*'  - wildcard patch: matches any tag starting with '0.9.'
      ''       - no constraint: returns the highest semver-looking tag
    """
    semver = re.compile(r"^\d+\.\d+\.\d+$")
    if not constraint:
        candidates = [t for t in tags if semver.match(t)]
        return max(candidates, key=_version_key) if candidates else ""

    prefix = constraint.rstrip("*").rstrip(".")
    candidates = [t for t in tags if t.startswith(prefix + ".")]
    return max(candidates, key=_version_key) if candidates else ""


def resolve_chart_images(chart_sources: list) -> list:
    """
    Resolve the latest OCI image tag for each chart matching its version constraint.
    Returns list of (chart_name, constraint, resolved_version).
    """
    resolved = []
    for chart, constraint in chart_sources:
        image = f"{VP_OCI_REGISTRY}/{chart}"
        label = constraint if constraint else "latest"
        print(f"  {chart} ({label})...", file=sys.stderr)
        tags = skopeo_list_tags(image)
        if not tags:
            print(f"    Warning: no tags found for {image}", file=sys.stderr)
            continue
        version = latest_matching_tag(tags, constraint)
        if not version:
            print(
                f"    Warning: no tag matching '{constraint}' for {image}",
                file=sys.stderr,
            )
            continue
        print(f"    → {version}", file=sys.stderr)
        resolved.append((chart, constraint, version))
    return resolved


RELEASES_SUFFIX = "releases-imageset-config.yaml"
OPERATORS_SUFFIX = "operators-imageset-config.yaml"
IMAGES_SUFFIX = "images-imageset-config.yaml"


def _imageset_path(prefix: str, suffix: str) -> str:
    """Return output path: PREFIX + suffix (prefix may be a directory path)."""
    return f"{prefix}{suffix}"


def _write_imageset_header(out: IO, ocp_full: str, section: str) -> None:
    """Write YAML header and mirror: opener for one ImageSetConfiguration section."""

    def w(line: str = "") -> None:
        out.write(line + "\n")

    w("# ImageSetConfiguration for the Layered Zero Trust Validated Pattern")
    w(f"# Section: {section}")
    w("#")
    w(f"# Cluster environment: OCP {ocp_full}")
    w("#")
    w("# Usage (run each config separately, or combine mirror steps as needed):")
    w("#   oc mirror --v2 --config <this-file> \\")
    w("#     docker://registry.internal.example.com \\")
    w("#     --remove-signatures=false \\")
    w("#     --workspace file:///path/to/mirror/output")
    w("#")
    w("# After mirroring, apply the generated IDMS/ITMS resources to the cluster:")
    w("#   oc apply -f oc-mirror-workspace/results-*/")
    w("#")
    w("apiVersion: mirror.openshift.io/v2alpha1")
    w("kind: ImageSetConfiguration")
    w("mirror:")


def write_releases_yaml(ocp_full: str, ocp_minor: str, out: IO) -> None:
    """Write OCP releases ImageSetConfiguration."""

    def w(line: str = "") -> None:
        out.write(line + "\n")

    _write_imageset_header(out, ocp_full, "OpenShift releases")
    w()
    w("  platform:")
    w("    channels:")
    w(f"    - name: stable-{ocp_minor}")
    w("      type: ocp")
    w(f'      minVersion: "{ocp_full}"')
    w(f'      maxVersion: "{ocp_full}"')
    w()


def write_operators_yaml(ocp_full: str, by_catalog: dict, out: IO) -> None:
    """Write operator catalog ImageSetConfiguration."""

    def w(line: str = "") -> None:
        out.write(line + "\n")

    _write_imageset_header(out, ocp_full, "operators")
    w()
    w("  operators:")
    w()

    for catalog_image in sorted(by_catalog):
        operators = sorted(by_catalog[catalog_image], key=lambda o: o["name"])
        w(f"  - catalog: {catalog_image}")
        w("    packages:")
        w()
        for op in operators:
            w(f'    - name: {op["name"]}')
            if op.get("defaultChannel"):
                w(f'      defaultChannel: {op["defaultChannel"]}')
            if op.get("channel"):
                w("      channels:")
                w(f'      - name: {op["channel"]}')
                if op.get("version"):
                    w(f'        minVersion: "{op["version"]}"')
        w()


def write_images_yaml(
    ocp_full: str,
    chart_images: list,
    workload_images: dict,
    out: IO,
) -> None:
    """Write additionalImages ImageSetConfiguration (charts + workload images)."""

    def w(line: str = "") -> None:
        out.write(line + "\n")

    _write_imageset_header(out, ocp_full, "individual images")
    w()
    w("  additionalImages:")

    if chart_images:
        w("  # Validated Patterns Helm charts (stored as OCI images)")
        for chart, constraint, version in sorted(chart_images, key=lambda x: x[0]):
            label = f"{chart} {constraint}" if constraint else chart
            w(f"  - name: {VP_OCI_REGISTRY}/{chart}:{version}  # {label}")
        w()

    by_ns: dict = defaultdict(list)
    for img, (ns, workload) in workload_images.items():
        by_ns[ns].append((img, workload))

    for ns in sorted(by_ns):
        w(f"  # Namespace: {ns}")
        seen_in_ns: set = set()
        for img, workload in sorted(by_ns[ns], key=lambda x: x[0]):
            if img in seen_in_ns:
                continue
            seen_in_ns.add(img)
            w(f"  - name: {img}  # {workload}")
    w()


def write_imageset_configs(
    prefix: str,
    ocp_full: str,
    ocp_minor: str,
    by_catalog: dict,
    chart_images: list,
    workload_images: dict,
) -> list[str]:
    """Write all three ImageSetConfiguration files and return their paths."""
    releases_path = _imageset_path(prefix, RELEASES_SUFFIX)
    operators_path = _imageset_path(prefix, OPERATORS_SUFFIX)
    images_path = _imageset_path(prefix, IMAGES_SUFFIX)

    with open(releases_path, "w") as f:
        write_releases_yaml(ocp_full, ocp_minor, f)
    with open(operators_path, "w") as f:
        write_operators_yaml(ocp_full, by_catalog, f)
    with open(images_path, "w") as f:
        write_images_yaml(ocp_full, chart_images, workload_images, f)

    return [releases_path, operators_path, images_path]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ImageSetConfiguration from a running ZTVP cluster"
    )
    parser.add_argument(
        "--prefix",
        "-p",
        metavar="PREFIX",
        default="",
        help=(
            "optional filename prefix for the three output files "
            f"({RELEASES_SUFFIX}, {OPERATORS_SUFFIX}, {IMAGES_SUFFIX})"
        ),
    )
    args = parser.parse_args()

    print("Detecting OCP version...", file=sys.stderr)
    ocp_full, ocp_minor = get_ocp_version()
    print(f"  OCP {ocp_full}", file=sys.stderr)

    print("Reading operator subscriptions...", file=sys.stderr)
    subscriptions = get_subscriptions()
    print(f"  {len(subscriptions)} subscriptions found", file=sys.stderr)

    print("Reading PackageManifests...", file=sys.stderr)
    package_manifests = get_package_manifests()
    print(f"  {len(package_manifests)} package manifests read", file=sys.stderr)

    print("Resolving catalog sources...", file=sys.stderr)
    # Merge catalog sources from OPERATORS list and live subscriptions
    unique_sources = {op.catalog_source for op in OPERATORS} | {
        sub["catalogSource"]
        for sub in subscriptions.values()
        if sub.get("catalogSource")
    }
    catalog_images = {src: get_catalog_image(src) for src in unique_sources}
    catalog_images = {k: v for k, v in catalog_images.items() if v}
    unique_catalogs = len(set(catalog_images.values()))
    print(f"  {unique_catalogs} catalog(s) identified", file=sys.stderr)

    by_catalog = build_catalog_groups(
        OPERATORS, subscriptions, package_manifests, catalog_images, ocp_minor
    )

    print("Detecting workload namespaces...", file=sys.stderr)
    namespaces = get_workload_namespaces()
    print(f"  Scanning: {', '.join(sorted(namespaces))}", file=sys.stderr)

    print("Collecting workload images...", file=sys.stderr)
    workload_images = collect_images(namespaces)
    print(f"  {len(workload_images)} unique image(s) found", file=sys.stderr)

    print("Resolving Validated Patterns Helm chart versions...", file=sys.stderr)
    chart_sources = get_helm_chart_sources()
    chart_images = resolve_chart_images(chart_sources)
    print(f"  {len(chart_images)} chart image(s) resolved", file=sys.stderr)

    paths = write_imageset_configs(
        args.prefix,
        ocp_full,
        ocp_minor,
        by_catalog,
        chart_images,
        workload_images,
    )
    for path in paths:
        print(f"Written {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
