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
import re
import sys
from collections import OrderedDict
from urllib.parse import urlparse

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


def _merge_namespace_dicts(base_dict, fragment_dict):
    """Merge namespace entries from fragment_dict into base_dict.

    Namespaces are now dictionaries where keys are namespace names and values
    are their configurations (or empty/None for namespaces without config).
    """
    for ns_name, ns_config in fragment_dict.items():
        if ns_name not in base_dict:
            # Add new namespace
            base_dict[ns_name] = copy.deepcopy(ns_config) if ns_config else None
        elif ns_config:
            # Merge configuration for existing namespace
            if base_dict[ns_name] is None:
                base_dict[ns_name] = copy.deepcopy(ns_config)
            elif isinstance(base_dict[ns_name], dict) and isinstance(ns_config, dict):
                _deep_merge_mappings(base_dict[ns_name], copy.deepcopy(ns_config))


def _is_named_list(lst):
    """Return True if lst is a list of mappings that all contain a 'name' key."""
    return len(lst) > 0 and all(
        isinstance(item, dict) and "name" in item for item in lst
    )


def _merge_named_lists(base_list, overlay_list):
    """Merge overlay items into base by 'name', replacing on conflict."""
    index = {item["name"]: i for i, item in enumerate(base_list)}
    for item in overlay_list:
        name = item["name"]
        if name in index:
            base_list[index[name]] = copy.deepcopy(item)
        else:
            index[name] = len(base_list)
            base_list.append(copy.deepcopy(item))


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
            if _is_named_list(base[key]) or _is_named_list(overlay[key]):
                _merge_named_lists(base[key], overlay[key])
            else:
                base[key].extend(overlay[key])
        else:
            base[key] = overlay[key]


def _apply_merge_into(base_apps, merge_into_spec, vault_jwt_roles_accumulator):
    """Handle merge_into_applications: merge fragment data into existing app configs.

    merge_into_spec is a mapping like:
        vault:
          jwt:
            roles: [...]
        ztvp-certificates:
          overrides: [...]

    For each target app, recursively merge into the existing app config.
    Named lists (items with a 'name' key) use upsert semantics; plain lists
    are appended.

    Special handling for vault JWT roles: instead of merging them into
    clusterGroup.applications.vault, accumulate them in vault_jwt_roles_accumulator
    for later merging into the overrides/values-vault-jwt.yaml structure.
    """
    for app_name, additions in merge_into_spec.items():
        # Special handling for vault JWT roles
        if app_name == "vault" and "jwt" in additions:
            jwt_config = additions.get("jwt", {})
            if "roles" in jwt_config:
                # Accumulate JWT roles for later merging into vault
                # override file
                vault_jwt_roles_accumulator.extend(copy.deepcopy(jwt_config["roles"]))
                # Remove jwt from additions to prevent it from being
                # merged into app config
                additions = copy.deepcopy(additions)
                del additions["jwt"]
                # If nothing else to merge, continue to next app
                if not additions:
                    continue

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


def merge_fragment(base, fragment, vault_jwt_roles_accumulator):
    """Merge a single feature fragment into the base YAML tree.

    vault_jwt_roles_accumulator is a list that collects JWT roles from all fragments
    for later merging into the vault override file.
    """
    if fragment is None:
        return

    for top_key in fragment:
        if top_key == "clusterGroup":
            _merge_cluster_group(
                base, fragment["clusterGroup"], vault_jwt_roles_accumulator
            )
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


def _merge_cluster_group(base, frag_cg, vault_jwt_roles_accumulator):
    """Merge clusterGroup sections with type-aware strategies.

    vault_jwt_roles_accumulator is a list that collects JWT roles from all fragments
    for later merging into the vault override file.
    """
    base_cg = base.setdefault("clusterGroup", {})

    if "namespaces" in frag_cg:
        base_ns = base_cg.setdefault("namespaces", {})
        # Ensure namespaces is a dict
        if not isinstance(base_ns, dict):
            print(
                f"WARNING: base namespaces is not a dict (type: {type(base_ns)}), "
                "converting to empty dict",
                file=sys.stderr,
            )
            base_ns = {}
            base_cg["namespaces"] = base_ns
        _merge_namespace_dicts(base_ns, frag_cg["namespaces"])

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
        _apply_merge_into(
            base_apps, frag_cg["merge_into_applications"], vault_jwt_roles_accumulator
        )


def validate_output(data):
    """Run basic sanity checks on the merged YAML tree."""
    cg = data.get("clusterGroup", {})

    ns_dict = cg.get("namespaces", {})
    if isinstance(ns_dict, dict):
        # Namespaces are now a dict, so duplicate checking is implicit
        # (dict keys are unique by definition)
        pass
    else:
        print(
            f"WARNING: namespaces is not a dict (type: {type(ns_dict)})",
            file=sys.stderr,
        )

    apps = cg.get("applications", {})
    for app_name, app_val in apps.items():
        overrides = app_val.get("overrides", []) if isinstance(app_val, dict) else []
        override_names = set()
        for ovr in overrides:
            name = ovr.get("name") if isinstance(ovr, dict) else None
            if name and name in override_names:
                print(
                    f"WARNING: duplicate override '{name}' in "
                    f"application '{app_name}'",
                    file=sys.stderr,
                )
            if name:
                override_names.add(name)

    # Vault JWT roles are now in overrides/values-vault-jwt.yaml
    # No need to validate them here as they're not in the generated variant


def _substitute_repository_placeholders(base, org=None, image_name=None):
    """Replace 'org' and 'image-name' placeholders in global.registry.repository."""
    repo = str(base.get("global", {}).get("registry", {}).get("repository", ""))
    if org:
        repo = repo.replace("org/", f"{org}/", 1)
    if image_name:
        repo = repo.replace("image-name", image_name)
    base["global"]["registry"]["repository"] = repo


GIT_REPO_PLACEHOLDER = "REPLACE_WITH_GIT_REPO_URL"
GIT_HOST_PLACEHOLDER = "REPLACE_WITH_GIT_HOST"
GIT_AUTH_TYPE_PLACEHOLDER = "REPLACE_WITH_GIT_AUTH_TYPE"
SSL_CA_ENABLED_PLACEHOLDER = "REPLACE_WITH_SSL_CA_ENABLED"
GIT_HOSTNAME_PLACEHOLDER = "REPLACE_WITH_GIT_HOSTNAME"

PUBLIC_GIT_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}

SSH_URL_RE = re.compile(r"^[\w.-]+@([\w.-]+):")


def _parse_git_repo_url(git_repo_url):
    """Derive (host, auth_type, hostname) from a Git repository URL.

    HTTPS URLs  -> host = "https://github.com",  auth_type = "https", hostname = "github.com"
    SSH URLs    -> host = "github.com",           auth_type = "ssh",   hostname = "github.com"
    """
    m = SSH_URL_RE.match(git_repo_url)
    if m:
        hostname = m.group(1)
        if not hostname:
            raise ValueError(f"Invalid SSH URL: {git_repo_url}")
        return hostname, "ssh", hostname
    parsed = urlparse(git_repo_url)
    if not parsed.hostname:
        raise ValueError(f"Invalid git URL (no hostname): {git_repo_url}")
    scheme = parsed.scheme or "https"
    hostname = parsed.hostname or ""
    return f"{scheme}://{hostname}", "https", hostname


def _substitute_git_overrides(
    base, git_repo_url, git_host, git_auth_type, git_hostname
):
    """Replace git-related placeholders in supply-chain and ztvp-certificates overrides."""
    apps = base.get("clusterGroup", {}).get("applications", {})
    is_internal = git_hostname not in PUBLIC_GIT_HOSTS

    sc = apps.get("supply-chain", {})
    sc_placeholder_map = {
        "qtodo.repository": (GIT_REPO_PLACEHOLDER, git_repo_url),
        "git.credentials.host": (GIT_HOST_PLACEHOLDER, git_host),
        "git.credentials.authType": (GIT_AUTH_TYPE_PLACEHOLDER, git_auth_type),
        "git.sslCABundle.enabled": (
            SSL_CA_ENABLED_PLACEHOLDER,
            "true" if is_internal else "false",
        ),
    }
    sc_overrides = sc.get("overrides", [])
    for override in sc_overrides:
        entry = sc_placeholder_map.get(override.get("name"))
        if entry and str(override.get("value")) == entry[0]:
            override["value"] = entry[1]

    # Remove git.sslCABundle.enabled override when false (public hosts)
    if not is_internal:
        sc_overrides[:] = [
            o
            for o in sc_overrides
            if not (
                o.get("name") == "git.sslCABundle.enabled" and o.get("value") == "false"
            )
        ]

    certs = apps.get("ztvp-certificates", {})
    certs_overrides = certs.get("overrides", [])
    if is_internal:
        for override in certs_overrides:
            if (
                override.get("name") == "customCA.remoteHosts[0]"
                and str(override.get("value")) == GIT_HOSTNAME_PLACEHOLDER
            ):
                override["value"] = git_hostname
    else:
        # Remove the remoteHosts placeholder for public hosts
        certs_overrides[:] = [
            o
            for o in certs_overrides
            if not (
                o.get("name") == "customCA.remoteHosts[0]"
                and str(o.get("value")) == GIT_HOSTNAME_PLACEHOLDER
            )
        ]


def _update_vault_jwt_override_file(override_file_path, new_roles):
    """Update the vault JWT override file with new roles from feature fragments.

    Merges new_roles into the vault_jwt_roles list in the override file.
    Uses named list semantics (upsert by role name).
    """
    if not new_roles:
        return

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 4096

    # Load existing override file
    if os.path.isfile(override_file_path):
        with open(override_file_path) as fh:
            override_data = yaml.load(fh)
    else:
        # Create new structure if file doesn't exist
        oidc_url = (
            "https://spire-spiffe-oidc-discovery-provider"
            ".zero-trust-workload-identity-manager.svc.cluster.local"
        )
        override_data = {
            "vault_jwt_config": True,
            "vault_jwt_policies": [],
            "vault_jwt_roles": [],
            "oidc_discovery_url": oidc_url,
        }

    # Get existing roles list
    existing_roles = override_data.setdefault("vault_jwt_roles", [])

    # Merge new roles using named list semantics
    _merge_named_lists(existing_roles, new_roles)

    # Write back to file
    with open(override_file_path, "w") as fh:
        yaml.dump(override_data, fh)

    role_names = [r.get("name", "unknown") for r in new_roles]
    print(f"  Updated {override_file_path} with roles: {', '.join(role_names)}")


def generate_variant(
    base_path,
    features_dir,
    resolved_features,
    registry_fragment_path,
    output_path,
    org=None,
    image_name=None,
    git_repo_url=None,
):
    """Load base, merge all feature fragments + registry option, write output."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 4096

    with open(base_path) as fh:
        base = yaml.load(fh)

    # Accumulator for vault JWT roles from feature fragments
    vault_jwt_roles_accumulator = []

    for feat_name in resolved_features:
        frag_path = os.path.join(features_dir, f"{feat_name}.yaml")
        if not os.path.isfile(frag_path):
            print(f"ERROR: fragment file not found: {frag_path}", file=sys.stderr)
            sys.exit(1)
        fragment = load_yaml_file(frag_path)
        merge_fragment(base, fragment, vault_jwt_roles_accumulator)

    if registry_fragment_path:
        if not os.path.isfile(registry_fragment_path):
            print(
                f"ERROR: registry fragment not found: {registry_fragment_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        registry_frag = load_yaml_file(registry_fragment_path)
        merge_fragment(base, registry_frag, vault_jwt_roles_accumulator)

    # Update vault JWT override file with roles from feature fragments
    if vault_jwt_roles_accumulator:
        repo_root = os.path.dirname(SCRIPT_DIR)
        override_file_path = os.path.join(
            repo_root, "overrides", "values-vault-jwt.yaml"
        )
        _update_vault_jwt_override_file(override_file_path, vault_jwt_roles_accumulator)

    if org or image_name:
        _substitute_repository_placeholders(base, org=org, image_name=image_name)

    if git_repo_url:
        git_host, git_auth_type, git_hostname = _parse_git_repo_url(git_repo_url)
        _substitute_git_overrides(
            base, git_repo_url, git_host, git_auth_type, git_hostname
        )

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
        suffix = "-protected-repos" if "protected-repos" in features else ""
        return f"values-hub-supply-chain-{label}{suffix}.yaml"
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
        "--git-repo",
        default=None,
        help="Private Git repository URL for protected-repos feature "
        "(e.g. https://github.com/your-org/qtodo.git)",
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

    needs_git_repo = any(
        feature_defs.get(f, {}).get("git_repo_required") for f in resolved
    )
    if needs_git_repo and not args.git_repo:
        print(
            "ERROR: --git-repo is required when protected-repos feature is enabled "
            "(e.g. --git-repo https://github.com/your-org/qtodo.git)",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Base:     {base}")
    print(f"Output:   {outdir}")
    print(f"Features: {' -> '.join(resolved)}")
    if args.registry_option:
        print(f"Registry: option {args.registry_option}")
    if args.git_repo:
        print(f"Git repo: {args.git_repo}")

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
                base,
                FEATURES_DIR,
                resolved,
                reg_path,
                out_path,
                org,
                image_name,
                git_repo_url=args.git_repo,
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
            base,
            FEATURES_DIR,
            resolved,
            reg_path,
            out_path,
            org,
            image_name,
            git_repo_url=args.git_repo,
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
