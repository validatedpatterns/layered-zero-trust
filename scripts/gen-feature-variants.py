#!/usr/bin/env python3
"""Generate values-hub.yaml variants by composing declarative feature fragments.

Features are defined as small YAML files under scripts/features/ that mirror the
values-hub.yaml structure.  Dependencies between features are resolved
automatically via the registry in scripts/features/features.yaml.

Prerequisites:
  pip install -r scripts/requirements.txt

Usage:
  # Single feature (auto-resolves deps: rhtpa -> storage)
  python3 scripts/gen-feature-variants.py --features rhtpa

  # Multiple features
  python3 scripts/gen-feature-variants.py --features rhtpa,rhtas

  # Full supply chain with built-in Quay (option 1)
  python3 scripts/gen-feature-variants.py --features supply-chain --registry-option 1

  # Full supply chain with BYO external registry (option 2)
  python3 scripts/gen-feature-variants.py --features supply-chain --registry-option 2

  # Full supply chain with embedded OpenShift image registry (option 3)
  python3 scripts/gen-feature-variants.py --features supply-chain --registry-option 3

  # Generate all 3 supply-chain registry variants at once
  python3 scripts/gen-feature-variants.py --features supply-chain --registry-option all

  # Custom base and output directory
  python3 scripts/gen-feature-variants.py \\
      --features rhtpa --base values-hub.yaml --outdir /tmp
"""

import argparse
import copy
import os
import sys
from collections import OrderedDict

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FEATURES_DIR = os.path.join(SCRIPT_DIR, "features")
REGISTRY_LABELS = {1: "quay", 2: "byo", 3: "embedded-openshift"}


def load_yaml_file(path):
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(path) as fh:
        return yaml.load(fh)


def _strip_comments(node):
    """Recursively remove all ruamel.yaml comments from a YAML subtree."""
    if isinstance(node, CommentedMap):
        node.ca.comment = None
        node.ca.items.clear()
        if hasattr(node.ca, "end"):
            node.ca.end = None
        for v in node.values():
            _strip_comments(v)
    elif isinstance(node, CommentedSeq):
        node.ca.comment = None
        node.ca.items.clear()
        if hasattr(node.ca, "end"):
            node.ca.end = None
        for item in node:
            _strip_comments(item)


def load_feature_registry():
    registry_path = os.path.join(FEATURES_DIR, "features.yaml")
    data = load_yaml_file(registry_path)
    return data["features"], data.get("registry_options", {})


def resolve_dependencies(requested, feature_defs):
    """Topological sort: expand requested features with their transitive deps."""
    resolved = OrderedDict()
    visiting = set()

    def visit(name):
        if name in resolved:
            return
        if name not in feature_defs:
            print(f"ERROR: unknown feature '{name}'", file=sys.stderr)
            sys.exit(1)
        if name in visiting:
            print(
                f"ERROR: circular dependency involving '{name}'",
                file=sys.stderr,
            )
            sys.exit(1)
        visiting.add(name)
        for dep in feature_defs[name].get("depends_on", []):
            visit(dep)
        visiting.discard(name)
        resolved[name] = True

    for feat in requested:
        visit(feat)
    return list(resolved.keys())


def _namespace_key(item):
    """Extract the unique key from a namespace list entry (string or mapping)."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        keys = list(item.keys())
        return keys[0] if keys else None
    return None


def _merge_namespace_lists(base_list, fragment_list):
    """Append namespace entries from fragment_list that are not already in base_list."""
    existing = {_namespace_key(item) for item in base_list}
    for item in fragment_list:
        key = _namespace_key(item)
        if key not in existing:
            base_list.append(item)
            existing.add(key)


def _deep_merge_mappings(base, overlay):
    """Recursively merge overlay into base (overlay wins for scalars)."""
    for key in overlay:
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(overlay[key], dict)
        ):
            _deep_merge_mappings(base[key], overlay[key])
        elif (
            key in base
            and isinstance(base[key], list)
            and isinstance(overlay[key], list)
        ):
            base[key].extend(overlay[key])
        else:
            base[key] = overlay[key]


def _apply_merge_into(base_apps, merge_into_spec):
    """Handle merge_into_applications: merge fragment data into existing app configs.

    merge_into_spec is a mapping like:
        vault:
          jwt:
            roles: [...]
        ztvp-certificates:
          overrides: [...]

    For each target app, recursively merge into the existing app config.
    Lists (roles, overrides) are appended rather than replaced.
    """
    for app_name, additions in merge_into_spec.items():
        if app_name not in base_apps:
            print(
                f"WARNING: merge_into_applications target '{app_name}'"
                " not found in base applications",
                file=sys.stderr,
            )
            continue
        _deep_merge_mappings(base_apps[app_name], copy.deepcopy(additions))


def _insert_key_before(mapping, new_key, new_value, before_key):
    """Insert new_key into a ruamel.yaml CommentedMap before before_key.

    ruamel.yaml mappings are ordered; plain assignment appends at the end.
    This rebuilds the ordering so new_key appears just before before_key.
    """
    if before_key not in mapping:
        mapping[new_key] = new_value
        return

    keys = list(mapping.keys())
    idx = keys.index(before_key)
    items = list(mapping.items())
    items.insert(idx, (new_key, new_value))
    for k in keys:
        del mapping[k]
    for k, v in items:
        mapping[k] = v


def merge_fragment(base, fragment):
    """Merge a single feature fragment into the base YAML tree."""
    if fragment is None:
        return

    for top_key in fragment:
        if top_key == "clusterGroup":
            _merge_cluster_group(base, fragment["clusterGroup"])
        elif top_key in base and isinstance(base[top_key], dict):
            _deep_merge_mappings(base[top_key], copy.deepcopy(fragment[top_key]))
        elif top_key not in base:
            _insert_key_before(
                base,
                top_key,
                copy.deepcopy(fragment[top_key]),
                "clusterGroup",
            )
        else:
            base[top_key] = copy.deepcopy(fragment[top_key])


def _merge_cluster_group(base, frag_cg):
    """Merge clusterGroup sections with type-aware strategies."""
    base_cg = base.setdefault("clusterGroup", {})

    if "namespaces" in frag_cg:
        base_ns = base_cg.setdefault("namespaces", [])
        _merge_namespace_lists(base_ns, frag_cg["namespaces"])

    if "subscriptions" in frag_cg:
        base_subs = base_cg.setdefault("subscriptions", {})
        for sub_name, sub_val in frag_cg["subscriptions"].items():
            if sub_name not in base_subs:
                base_subs[sub_name] = copy.deepcopy(sub_val)

    if "applications" in frag_cg:
        base_apps = base_cg.setdefault("applications", {})
        for app_name, app_val in frag_cg["applications"].items():
            if app_name not in base_apps:
                base_apps[app_name] = copy.deepcopy(app_val)

    if "merge_into_applications" in frag_cg:
        base_apps = base_cg.get("applications", {})
        _apply_merge_into(base_apps, frag_cg["merge_into_applications"])


def validate_output(data):
    """Run basic sanity checks on the merged YAML tree."""
    cg = data.get("clusterGroup", {})

    ns_list = cg.get("namespaces", [])
    seen = set()
    for item in ns_list:
        key = _namespace_key(item)
        if key in seen:
            print(f"WARNING: duplicate namespace '{key}'", file=sys.stderr)
        seen.add(key)

    apps = cg.get("applications", {})
    vault = apps.get("vault", {})
    jwt_roles = vault.get("jwt", {}).get("roles", [])
    role_names = set()
    for role in jwt_roles:
        name = role.get("name")
        if name in role_names:
            print(f"WARNING: duplicate vault JWT role '{name}'", file=sys.stderr)
        role_names.add(name)


def _substitute_repository_placeholders(base, org=None, image_name=None):
    """Replace 'org' and 'image-name' placeholders in global.registry.repository."""
    repo = str(base.get("global", {}).get("registry", {}).get("repository", ""))
    if org:
        repo = repo.replace("org/", f"{org}/", 1)
    if image_name:
        repo = repo.replace("image-name", image_name)
    base["global"]["registry"]["repository"] = repo


def generate_variant(
    base_path,
    features_dir,
    resolved_features,
    registry_fragment_path,
    output_path,
    org=None,
    image_name=None,
):
    """Load base, merge all feature fragments + registry option, write output."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 4096

    with open(base_path) as fh:
        base = yaml.load(fh)

    for feat_name in resolved_features:
        frag_path = os.path.join(features_dir, f"{feat_name}.yaml")
        if not os.path.isfile(frag_path):
            print(f"ERROR: fragment file not found: {frag_path}", file=sys.stderr)
            sys.exit(1)
        fragment = load_yaml_file(frag_path)
        merge_fragment(base, fragment)

    if registry_fragment_path:
        if not os.path.isfile(registry_fragment_path):
            print(
                f"ERROR: registry fragment not found: {registry_fragment_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        registry_frag = load_yaml_file(registry_fragment_path)
        merge_fragment(base, registry_frag)

    if org or image_name:
        _substitute_repository_placeholders(base, org=org, image_name=image_name)

    validate_output(base)
    cg = base.get("clusterGroup")
    if cg:
        for key in ("namespaces", "subscriptions", "applications"):
            if key in cg:
                _strip_comments(cg[key])

    with open(output_path, "w") as fh:
        yaml.dump(base, fh)

    print(f"  -> {output_path}")


def build_output_name(features, registry_option=None):
    """Construct the output filename from features and optional registry option."""
    if "supply-chain" in features:
        label = REGISTRY_LABELS.get(registry_option, f"option-{registry_option}")
        return f"values-hub-supply-chain-{label}.yaml"
    return f"values-hub-{'-'.join(features)}.yaml"


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--features",
        default=None,
        help="Comma-separated list of features to enable (e.g. rhtpa,rhtas)",
    )
    parser.add_argument(
        "--registry-option",
        default=None,
        help=(
            "Registry option for supply-chain: "
            "1=built-in Quay, "
            "2=BYO/external registry, "
            "3=embedded OpenShift image registry, "
            "'all'=generate all 3 variants"
        ),
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
        "--list-features",
        action="store_true",
        help="List available features and exit",
    )
    args = parser.parse_args()

    feature_defs, registry_opts = load_feature_registry()

    if args.list_features:
        print("Available features:")
        for name, info in feature_defs.items():
            deps = ", ".join(info.get("depends_on", [])) or "none"
            print(f"  {name:20s} - {info['description']}  (deps: {deps})")
        if registry_opts:
            print("\nRegistry options (for --registry-option with supply-chain):")
            for num, info in registry_opts.items():
                print(f"  {num} = {info['label']}")
        sys.exit(0)

    if not args.features:
        parser.error("--features is required (or use --list-features)")

    repo_root = os.path.dirname(SCRIPT_DIR)
    base = args.base or os.path.join(repo_root, "values-hub.yaml")
    outdir = args.outdir or "/tmp"

    if not os.path.isfile(base):
        print(f"ERROR: base file not found: {base}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(outdir, exist_ok=True)

    requested = [f.strip() for f in args.features.split(",")]
    resolved = resolve_dependencies(requested, feature_defs)

    org = None
    image_name = None
    repo_feature = None
    for f in resolved:
        val = feature_defs.get(f, {}).get("org")
        if val:
            org = val
            repo_feature = f
        val = feature_defs.get(f, {}).get("image_name")
        if val:
            image_name = val
            repo_feature = f

    needs_registry = any(
        feature_defs.get(f, {}).get("registry_option_required") for f in resolved
    )
    if needs_registry and not args.registry_option:
        print(
            "ERROR: --registry-option is required when supply-chain feature is enabled "
            "(use 1, 2, 3, or 'all')",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Base:     {base}")
    print(f"Output:   {outdir}")
    print(f"Features: {' -> '.join(resolved)}")
    if args.registry_option:
        print(f"Registry: option {args.registry_option}")

    if args.registry_option == "all":
        for opt_num in [1, 2, 3]:
            opt_key = opt_num
            opt_info = registry_opts.get(opt_key)
            if not opt_info:
                print(
                    f"ERROR: no registry option {opt_key} in features.yaml",
                    file=sys.stderr,
                )
                sys.exit(1)
            reg_path = os.path.join(FEATURES_DIR, opt_info["file"])
            out_name = build_output_name(requested, opt_num)
            out_path = os.path.join(outdir, out_name)
            generate_variant(
                base, FEATURES_DIR, resolved, reg_path, out_path, org, image_name
            )
    else:
        reg_path = None
        if args.registry_option:
            opt_num = int(args.registry_option)
            opt_info = registry_opts.get(opt_num)
            if not opt_info:
                print(
                    f"ERROR: no registry option {opt_num} in features.yaml",
                    file=sys.stderr,
                )
                sys.exit(1)
            reg_path = os.path.join(FEATURES_DIR, opt_info["file"])

        out_name = build_output_name(
            requested,
            int(args.registry_option) if args.registry_option else None,
        )
        out_path = os.path.join(outdir, out_name)
        generate_variant(
            base, FEATURES_DIR, resolved, reg_path, out_path, org, image_name
        )

    if args.registry_option and org and image_name:
        print(
            f"\nNote: The '{repo_feature}' feature defines org '{org}' and"
            f" image_name '{image_name}', so the\n"
            f"      generated repository has been set to"
            f" '{org}/{image_name}' automatically."
        )
    elif args.registry_option:
        print(
            "\nNote: The generated 'repository' value uses generic"
            " 'org/image-name' placeholders.\n"
            "      Replace them with the actual org and image name"
            " before applying the file."
        )

    print("Done.")


if __name__ == "__main__":
    main()
