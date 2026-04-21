#!/usr/bin/env python3
"""Generate values-hub.yaml variants for BYO container registry options.

Reads the default values-hub.yaml (all supply-chain components commented out)
and produces up to 3 variants with the chosen registry option enabled:

  Option 1: Built-in Quay Registry
  Option 2: BYO / External Registry (e.g. quay.io, ghcr.io)
  Option 3: Embedded OpenShift Image Registry

Each variant also enables the common supply-chain stack (OpenShift Pipelines,
ODF, NooBaa, RHTAS, RHTPA, and their namespaces/subscriptions/vault roles).

Registry credentials are centralized in a single `global.registry` block at
the top of values-hub.yaml.  Both the supply-chain and qtodo charts fall back
to `global.registry.*` when their local registry values are empty.

Usage:
  # Generate all 3 variants under /tmp
  python3 scripts/gen-byo-container-registry-variants.py

  # Generate a single variant
  python3 scripts/gen-byo-container-registry-variants.py --option 2

  # Custom base file and output directory
  python3 scripts/gen-byo-container-registry-variants.py \\
      --base my-values-hub.yaml --outdir /tmp/variants
"""

import argparse
import os
import re
import sys


def uncomment_line(line):
    """Remove one layer of comment: '    # foo' -> '    foo'."""
    return re.sub(r"^(\s*)# ?", r"\1", line, count=1)


def uncomment_lines_matching(lines, patterns):
    """Uncomment individual lines matching any of the given patterns."""
    result = []
    for line in lines:
        matched = False
        for pat in patterns:
            if re.search(pat, line):
                result.append(uncomment_line(line))
                matched = True
                break
        if not matched:
            result.append(line)
    return result


def _uncomment_multiline_block(lines, trigger_re, body_re):
    """Uncomment a contiguous block: first line matches *trigger_re*,
    subsequent lines match *body_re*.  Both the trigger and body
    lines are uncommented."""
    new = []
    i = 0
    while i < len(lines):
        if re.search(trigger_re, lines[i]):
            while i < len(lines) and re.search(body_re, lines[i]):
                new.append(uncomment_line(lines[i]))
                i += 1
            continue
        new.append(lines[i])
        i += 1
    return new


def _uncomment_until_sentinel(lines, trigger_re, sentinel_re, prev_re=None):
    """Uncomment from trigger line until a sentinel (exclusive)."""
    new = []
    i = 0
    while i < len(lines):
        prev_ok = prev_re is None or (i > 0 and re.search(prev_re, lines[i - 1]))
        if re.search(trigger_re, lines[i]) and prev_ok:
            while i < len(lines):
                if re.match(r"^\s*$", lines[i]):
                    break
                if re.match(r"^\s{4}\w", lines[i]):
                    break
                if re.search(sentinel_re, lines[i]):
                    break
                new.append(uncomment_line(lines[i]))
                i += 1
            continue
        new.append(lines[i])
        i += 1
    return new


# ---------------------------------------------------------------------------
# Global registry block
# ---------------------------------------------------------------------------
def enable_global_registry(lines, option_num):
    """Uncomment the global.registry block for the selected option.

    The base file contains three commented blocks:
        # OPTION 1: Built-in Quay Registry
        # global:
        #   registry:
        #     ...
        # OPTION 2: ...
        # global:
        #   registry:
        #     ...
        # OPTION 3: ...
        # global:
        #   registry:
        #     ...

    This function uncomments only the block matching option_num.
    """
    target_header = f"# OPTION {option_num}:"
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if re.search(re.escape(target_header), line):
            result.append(line)
            i += 1
            while i < len(lines):
                if re.match(r"^# OPTION \d+:", lines[i]):
                    break
                if re.match(r"^$", lines[i]):
                    break
                if re.match(r"^[^#]", lines[i]):
                    break
                result.append(uncomment_line(lines[i]))
                i += 1
            continue

        result.append(line)
        i += 1
    return result


# ---------------------------------------------------------------------------
# Supply-chain app enabler
# ---------------------------------------------------------------------------
def enable_supply_chain_app(lines, option_num):
    """Enable the supply-chain app and its option-specific overrides.

    Pass 1: strip one comment layer from all supply-chain block lines.
    Pass 2: selectively uncomment option-specific and common overrides.
    """
    # --- Pass 1: strip outer comment from all supply-chain lines ----------
    pass1 = []
    in_block = False
    block_start = -1
    block_end = -1

    for idx, line in enumerate(lines):
        if re.search(r"# Secure Supply Chain - Uncomment to enable", line):
            in_block = True
            block_start = idx + 1
            pass1.append(line)
            continue
        if in_block and re.match(r"^\s{4}#\s*$", line):
            in_block = False
            block_end = idx
            pass1.append(line)
            continue
        if in_block:
            pass1.append(uncomment_line(line))
        else:
            pass1.append(line)

    if block_start < 0:
        return pass1

    # --- Pass 2: selectively uncomment option overrides -------------------
    final = []
    for idx, line in enumerate(pass1):
        if not (block_start <= idx < block_end):
            final.append(line)
            continue

        stripped = line.lstrip()
        if not stripped.startswith("#"):
            final.append(line)
            continue

        # Always uncomment RHTAS and RHTPA flags
        if re.search(r"# - name: rhtas\.enabled", line) or re.search(
            r"# - name: rhtpa\.enabled", line
        ):
            final.append(uncomment_line(line))
            continue
        if re.search(r"#\s+value:", line) and final:
            prev = final[-1]
            if "rhtas.enabled" in prev or "rhtpa.enabled" in prev:
                final.append(uncomment_line(line))
                continue

        # Option 1 (Built-in Quay): uncomment quay.enabled and tlsVerify
        if option_num == 1:
            if re.search(r"# - name: quay\.enabled", line) or re.search(
                r"# - name: registry\.tlsVerify", line
            ):
                final.append(uncomment_line(line))
                continue
            if re.search(r"#\s+value:", line) and final:
                prev = final[-1]
                if "quay.enabled" in prev or "registry.tlsVerify" in prev:
                    final.append(uncomment_line(line))
                    continue

        # Option 3 (Embedded OpenShift): uncomment ensureImageNamespaceRBAC
        if option_num == 3:
            if re.search(r"# - name: registry\.embeddedOpenShift", line):
                final.append(uncomment_line(line))
                continue
            if re.search(r"#\s+value:", line) and final:
                prev = final[-1]
                if "embeddedOpenShift" in prev:
                    final.append(uncomment_line(line))
                    continue

        final.append(line)

    return final


# ---------------------------------------------------------------------------
# Common supply-chain components (shared by all 3 options)
# ---------------------------------------------------------------------------
def apply_common_supply_chain(lines):
    """Uncomment all components common to every supply-chain option."""

    # Namespace: openshift-pipelines
    lines = uncomment_lines_matching(lines, [r"^\s*# - openshift-pipelines\s*$"])

    # Namespace: openshift-storage
    lines = _uncomment_multiline_block(
        lines,
        r"# - openshift-storage:",
        r"#\s+(- openshift-storage:|operatorGroup:|targetNamespace:"
        r"|annotations:|labels:"
        r"|openshift\.io/cluster-monitoring"
        r"|argocd\.argoproj\.io/sync-wave.*26)",
    )

    # Namespace: trusted-artifact-signer
    lines = _uncomment_multiline_block(
        lines,
        r"# - trusted-artifact-signer:",
        r"#\s+(- trusted-artifact-signer:"
        r"|annotations:|labels:"
        r"|argocd\.argoproj\.io/sync-wave.*32.*Auto-created"
        r"|openshift\.io/cluster-monitoring)",
    )

    # Namespace: rhtpa-operator
    lines = _uncomment_multiline_block(
        lines,
        r"# - rhtpa-operator:",
        r"#\s+(- rhtpa-operator:|operatorGroup:"
        r"|targetNamespace: rhtpa"
        r"|annotations:"
        r"|argocd\.argoproj\.io/sync-wave.*26.*Create before operator)",
    )

    # Namespace: trusted-profile-analyzer
    lines = _uncomment_multiline_block(
        lines,
        r"# - trusted-profile-analyzer:",
        r"#\s+(- trusted-profile-analyzer:"
        r"|annotations:|labels:"
        r"|argocd\.argoproj\.io/sync-wave.*32.*Create before RHTPA"
        r"|openshift\.io/cluster-monitoring)",
    )

    # Subscription: openshift-pipelines
    new = []
    i = 0
    while i < len(lines):
        prev = lines[i - 1] if i > 0 else ""
        if re.search(r"# openshift-pipelines:", lines[i]) and re.search(
            r"Uncomment to enable OpenShift Pipelines", prev
        ):
            while i < len(lines) and re.search(
                r"#\s*(openshift-pipelines:"
                r"|name: openshift-pipelines"
                r"|namespace: openshift-operators)",
                lines[i],
            ):
                new.append(uncomment_line(lines[i]))
                i += 1
            continue
        new.append(lines[i])
        i += 1
    lines = new

    # Subscription: odf
    lines = _uncomment_multiline_block(
        lines,
        r"# odf:",
        r"#\s*(odf:|name: odf-operator|namespace: openshift-storage"
        r"|channel: stable-4"
        r"|annotations:"
        r"|argocd\.argoproj\.io/sync-wave.*27.*Install after OperatorGroup)",
    )

    # Subscription: rhtas-operator
    lines = _uncomment_multiline_block(
        lines,
        r"# rhtas-operator:",
        r"#\s*(rhtas-operator:|name: rhtas-operator"
        r"|namespace: openshift-operators|channel: stable-v1\.3"
        r"|annotations:"
        r"|argocd\.argoproj\.io/sync-wave.*29"
        r"|catalogSource: redhat-operators)",
    )

    # Subscription: rhtpa-operator
    new = []
    i = 0
    while i < len(lines):
        prev2 = lines[i - 2] if i > 1 else ""
        if re.search(r"# rhtpa-operator:", lines[i]) and re.search(r"Channel:", prev2):
            while i < len(lines) and re.search(
                r"#\s*(rhtpa-operator:|name: rhtpa-operator"
                r"|namespace: rhtpa-operator"
                r"|channel: stable-v1\.1"
                r"|catalogSource: redhat-operators"
                r"|annotations:"
                r"|argocd\.argoproj\.io/sync-wave.*27"
                r".*Install after OperatorGroup.*before applications)",
                lines[i],
            ):
                new.append(uncomment_line(lines[i]))
                i += 1
            continue
        new.append(lines[i])
        i += 1
    lines = new

    # Vault JWT roles: rhtpa and supply-chain
    lines = uncomment_lines_matching(
        lines,
        [
            r"#\s+- name: rhtpa\s*$",
            r"#\s+audience: rhtpa",
            r"#\s+subject: spiffe://.*ns/trusted-profile-analyzer",
            r"#\s+policies:\s*$",
            r"#\s+- hub-infra-rhtpa-jwt-secret",
            r"#\s+- name: supply-chain\s*$",
            r"#\s+audience: supply-chain",
            r"#\s+subject: spiffe://.*sa/pipeline",
            r"#\s+- hub-supply-chain-jwt-secret",
        ],
    )

    # Application: noobaa-mcg
    lines = _uncomment_multiline_block(
        lines,
        r"# noobaa-mcg:",
        r"#\s*(noobaa-mcg:|name: noobaa-mcg|namespace: openshift-storage"
        r"|project: hub|path: charts/noobaa-mcg|annotations:"
        r"|argocd\.argoproj\.io/sync-wave.*36)",
    )

    # Application: trusted-artifact-signer
    lines = _uncomment_until_sentinel(
        lines,
        r"# trusted-artifact-signer:",
        r"# RHTPA \(Red Hat",
        prev_re=r"Depends on:",
    )

    # Application: trusted-profile-analyzer
    lines = _uncomment_until_sentinel(
        lines,
        r"# trusted-profile-analyzer:",
        r"PLACEHOLDER_NEVER_MATCH",
        prev_re=r"Depends on:",
    )

    return lines


# ---------------------------------------------------------------------------
# Per-option enablers
# ---------------------------------------------------------------------------
def enable_quay_namespace_and_sub(lines):
    """Enable quay-enterprise namespace, quay-operator sub, quay-registry app."""

    lines = _uncomment_multiline_block(
        lines,
        r"# - quay-enterprise:",
        r"#\s+(- quay-enterprise:"
        r"|annotations:|labels:"
        r"|argocd\.argoproj\.io/sync-wave.*32.*Create before"
        r"|openshift\.io/cluster-monitoring)",
    )

    lines = _uncomment_multiline_block(
        lines,
        r"# quay-operator:",
        r"#\s*(quay-operator:|name: quay-operator"
        r"|namespace: openshift-operators|channel: stable-3"
        r"|annotations:"
        r"|argocd\.argoproj\.io/sync-wave.*28)",
    )

    lines = _uncomment_multiline_block(
        lines,
        r"# quay-registry:",
        r"#\s*(quay-registry:|name: quay-registry"
        r"|namespace: quay-enterprise|project: hub"
        r"|chart: quay|chartVersion: 0\.1|annotations:"
        r"|argocd\.argoproj\.io/sync-wave.*41)",
    )

    return lines


def enable_image_pull_trust(lines, hostname):
    """Enable imagePullTrust in ztvp-certificates overrides."""
    result = []
    for line in lines:
        if re.search(r"# - name: imagePullTrust\.enabled", line):
            result.append(uncomment_line(line))
        elif (
            re.search(r'#\s+value: "true"\s*$', line)
            and result
            and "imagePullTrust.enabled" in result[-1]
        ):
            result.append(uncomment_line(line))
        elif re.search(r"# - name: imagePullTrust\.registries\[0\]", line):
            result.append(uncomment_line(line))
        elif (
            re.search(r"#\s+value:", line)
            and result
            and "imagePullTrust.registries" in result[-1]
        ):
            result.append(re.sub(r"#\s+value:.*", f"  value: {hostname}", line))
        else:
            result.append(line)
    return result


# ---------------------------------------------------------------------------
# Top-level generator
# ---------------------------------------------------------------------------
OPTION_LABELS = {
    1: "built-in-quay-registry",
    2: "byo-external-registry",
    3: "embedded-openshift-registry",
}


def generate_variant(base_path, option_num, output_path):
    with open(base_path) as fh:
        lines = fh.readlines()

    lines = apply_common_supply_chain(lines)
    lines = enable_global_registry(lines, option_num)
    lines = enable_supply_chain_app(lines, option_num)

    if option_num == 1:
        lines = enable_quay_namespace_and_sub(lines)
        lines = enable_image_pull_trust(
            lines,
            "quay-registry-quay-quay-enterprise.apps."
            "{{ $.Values.global.clusterDomain }}",
        )

    if option_num == 3:
        lines = enable_image_pull_trust(
            lines,
            "default-route-openshift-image-registry.apps."
            "{{ $.Values.global.clusterDomain }}",
        )

    with open(output_path, "w") as fh:
        fh.writelines(lines)

    label = OPTION_LABELS.get(option_num, f"option-{option_num}")
    print(f"  Option {option_num} ({label}) -> {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Base values-hub.yaml to read (default: <repo>/values-hub.yaml)",
    )
    parser.add_argument(
        "--outdir",
        default=None,
        help="Output directory (default: /tmp)",
    )
    parser.add_argument(
        "--option",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Generate only this option (default: all 3)",
    )
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = args.base or os.path.join(repo_root, "values-hub.yaml")
    outdir = args.outdir or "/tmp"

    if not os.path.isfile(base):
        print(f"ERROR: base file not found: {base}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(outdir, exist_ok=True)

    options = [args.option] if args.option else [1, 2, 3]
    print(f"Base: {base}")
    print(f"Output directory: {outdir}")
    for opt in options:
        label = OPTION_LABELS[opt]
        out = os.path.join(outdir, f"values-hub-{label}.yaml")
        generate_variant(base, opt, out)

    print("Done.")


if __name__ == "__main__":
    main()
