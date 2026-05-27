# Feature Variant Generator

`gen-feature-variants.py` generates `values-hub.yaml` variants by composing
declarative feature fragments. Features live as small YAML files under
`scripts/features/` and dependencies between them are resolved automatically.

## Prerequisites

* Python 3.9+
* `ruamel.yaml` library

## Environment Setup

### Option A: virtualenv (recommended)

```bash
cd layered-zero-trust
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
```

### Option B: system-wide pip

```bash
pip install --user -r scripts/requirements.txt
```

### Option C: container (Podman / Docker)

```bash
podman run --rm -it \
  -v "$(pwd):/work:Z" -w /work \
  python:3.12-slim \
  bash -c "pip install -r scripts/requirements.txt && \
           python3 scripts/gen-feature-variants.py --list-features"
```

## Usage

```bash
# List available features and registry options
python3 scripts/gen-feature-variants.py --list-features

# Enable a single feature (dependencies are resolved automatically)
python3 scripts/gen-feature-variants.py --features rhtpa

# Enable multiple features
python3 scripts/gen-feature-variants.py --features rhtpa,rhtas

# Enable Tekton Chains (auto-resolves: pipelines -> rhtas -> tekton-chains)
python3 scripts/gen-feature-variants.py --features tekton-chains

# Full supply chain: pick a registry option (1, 2, or 3)
python3 scripts/gen-feature-variants.py --features supply-chain --registry-option 1

# Generate all three supply-chain registry variants at once
python3 scripts/gen-feature-variants.py --features supply-chain --registry-option all

# Supply chain with protected (private) Git repository support
python3 scripts/gen-feature-variants.py \
    --features supply-chain,protected-repos \
    --registry-option 2 \
    --git-repo https://github.com/your-org/qtodo.git

# Custom base file and output directory
python3 scripts/gen-feature-variants.py \
    --features rhtpa --base values-hub.yaml --outdir /tmp
```

Generated files are written to `/tmp` by default (override with `--outdir`).
The output directory is created automatically if it does not exist.

## Registry Options (supply-chain only)

| Option | Description                 | Notes                                      |
| ------ | --------------------------- | ------------------------------------------ |
| 1      | Built-in Quay registry      | Deploys Quay inside the cluster            |
| 2      | BYO / external registry     | Uses an external registry (e.g. quay.io)   |
| 3      | Embedded OpenShift image registry | Uses the built-in OpenShift image registry |

> **Note:** The registry option fragments use generic `org/image-name`
> placeholders in the `repository` field. When a feature defines `org`
> and `image_name` (the `supply-chain` feature sets them to `ztvp` and
> `qtodo`), the generator replaces both placeholders automatically, so
> the output already contains `ztvp/qtodo`. If you use a custom feature
> without these fields, replace the placeholders manually before applying
> the generated file.

## Protected Repositories (`--git-repo`)

When the `protected-repos` feature is enabled, the `--git-repo` argument is
**required**. It specifies the private Git repository URL that the Tekton
pipeline will clone. The generator auto-detects the authentication mode
(HTTPS or SSH) from the URL scheme and sets `git.credentials.authType` and
`git.credentials.host` accordingly:

```bash
# HTTPS (basic-auth with username + PAT)
python3 scripts/gen-feature-variants.py \
    --features supply-chain,protected-repos \
    --registry-option 1 \
    --git-repo https://github.com/your-org/qtodo.git

# SSH (key-based auth)
python3 scripts/gen-feature-variants.py \
    --features supply-chain,protected-repos \
    --registry-option 1 \
    --git-repo git@github.com:your-org/qtodo.git
```

For an **HTTPS** URL the generated `values-hub.yaml` will include:

```yaml
- name: git.credentials.authType
  value: "https"
- name: git.credentials.host
  value: "https://github.com"
```

For an **SSH** URL:

```yaml
- name: git.credentials.authType
  value: "ssh"
- name: git.credentials.host
  value: "github.com"
```

See [Protected Repositories](../docs/supply-chain.md#protected-repositories)
for the full setup (Vault credentials, ExternalSecret, workspace selection).

## How It Works

1. The script reads the base `values-hub.yaml`.
2. For each requested feature it loads the matching fragment from
   `scripts/features/<feature>.yaml` and merges it into the base tree.
3. `clusterGroup` sections use type-aware merge strategies:
   * **namespaces**: appended only if not already present
   * **subscriptions / applications**: add-if-absent
   * **merge_into_applications**: deep-merge into _existing_ application
     configs (e.g. adding Vault JWT roles or chart overrides)
4. Comments inside `clusterGroup.namespaces`, `clusterGroup.subscriptions`,
   and `clusterGroup.applications` are stripped from the generated output to
   avoid confusion from commented-out blocks mixing with merged content.
   All other comments (top-level headers, `spire`, `sharedValueFiles`,
   `imperative`, etc.) are preserved as-is.
5. Basic validation checks for duplicates before writing the result.

## Adding a New Feature

1. Create `scripts/features/<name>.yaml` mirroring the `values-hub.yaml`
   structure (namespaces, subscriptions, applications).
2. Register it in `scripts/features/features.yaml` with a description and
   any `depends_on` entries.
3. If the feature needs to modify an existing application (e.g. add a Vault
   JWT role), use the `merge_into_applications` key under `clusterGroup`.
