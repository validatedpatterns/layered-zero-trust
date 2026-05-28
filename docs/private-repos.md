# Deploying from a Private Repository

This document describes how to deploy the Layered Zero Trust Validated Pattern
from a private Git repository.

The Validated Patterns framework supports deploying from both SSH-secured and
HTTPS-secured (PAT) private repositories.  The mechanism works by creating an
ArgoCD repository secret **before** the pattern is deployed, so that both the
Cluster ArgoCD and Hub ArgoCD instances can pull the pattern manifests.

> [!NOTE]
> The upstream documentation is at
> <https://validatedpatterns.io/learn/private-repos/>.  This page provides
> ZTVP-specific guidance that builds on the framework docs.

## Prerequisites

* An OpenShift 4.16+ cluster with `oc` CLI access
* A fork or private copy of this repository
* A deploy key (SSH) or Personal Access Token (HTTPS) with **read** access

## Option A: SSH Key Authentication

### 1. Generate a deploy key

```shell
ssh-keygen -t ed25519 -f ~/.ssh/ztvp-deploy-key -N ""
```

### 2. Register the public key

Add `~/.ssh/ztvp-deploy-key.pub` as a **deploy key** in your Git hosting
provider (GitHub Settings -> Deploy keys, GitLab Settings -> Repository ->
Deploy keys, etc.).

### 3. Configure values-secret

Copy the template and uncomment the SSH `bootstrap_secrets` block:

```shell
cp values-secret.yaml.template ~/values-secret-layered-zero-trust.yaml
```

Edit `~/values-secret-layered-zero-trust.yaml` and uncomment **Option A**
under the "BOOTSTRAP SECRETS" section.  Update the `url` field with your
repository's SSH URL:

```yaml
bootstrap_secrets:
- name: private-repo
  targetNamespaces:
  - openshift-operators
  labels:
    argocd.argoproj.io/secret-type: repository
  fields:
  - name: type
    value: git
  - name: url
    value: git@github.com:YOUR-ORG/layered-zero-trust.git
  - name: sshPrivateKey
    path: ~/.ssh/ztvp-deploy-key
```

### 4. Deploy

```shell
./pattern.sh make TOKEN_SECRET=private-repo TOKEN_NAMESPACE=openshift-operators install
```

## Option B: HTTPS with Personal Access Token (PAT)

### 1. Create a PAT

* **GitHub:** Settings -> Developer settings -> Personal access tokens ->
  Fine-grained tokens.  Grant **Contents: Read** on the target repository.
* **GitLab:** Settings -> Access Tokens.  Grant `read_repository` scope.

Store the token in a local file:

```shell
mkdir -p ~/.config/validated-patterns
echo -n "ghp_xxxxxxxxxxxxxxxxxxxx" > ~/.config/validated-patterns/git-pat
chmod 600 ~/.config/validated-patterns/git-pat
```

### 2. Configure values-secret

Copy the template and uncomment the HTTPS `bootstrap_secrets` block:

```shell
cp values-secret.yaml.template ~/values-secret-layered-zero-trust.yaml
```

Edit `~/values-secret-layered-zero-trust.yaml` and uncomment **Option B**
under the "BOOTSTRAP SECRETS" section.  Update the `url`, `username`, and
`password` path:

```yaml
bootstrap_secrets:
- name: private-repo
  targetNamespaces:
  - openshift-operators
  labels:
    argocd.argoproj.io/secret-type: repository
  fields:
  - name: type
    value: git
  - name: url
    value: https://github.com/YOUR-ORG/layered-zero-trust.git
  - name: username
    value: YOUR-USERNAME
  - name: password
    path: ~/.config/validated-patterns/git-pat
```

> [!NOTE]
> For GitLab, the `username` must be `oauth2`, not your GitLab handle.

### 3. Deploy

```shell
./pattern.sh make TOKEN_SECRET=private-repo TOKEN_NAMESPACE=openshift-operators install
```

## How It Works

1. The `bootstrap_secrets` section in `values-secret.yaml` instructs the
   Validated Patterns framework to create the `private-repo` Kubernetes
   Secret in the `openshift-operators` namespace **before** deploying the
   pattern.

2. The `argocd.argoproj.io/secret-type: repository` label tells ArgoCD to
   pick up the secret as a repository credential.

3. The `TOKEN_SECRET` and `TOKEN_NAMESPACE` Make variables set the
   `tokenSecret` and `tokenSecretNamespace` fields on the Pattern Custom
   Resource, which propagates the credentials to all ArgoCD instances
   managed by the pattern.

## Verifying

After deployment, confirm the repository secret was created:

```shell
oc get secret private-repo -n openshift-operators \
  -o jsonpath='{.metadata.labels.argocd\.argoproj\.io/secret-type}'
```

Expected output: `repository`

Check the Cluster ArgoCD can see the repository:

```shell
oc get application layered-zero-trust-hub -n openshift-gitops \
  -o jsonpath='{.status.sync.status}'
```

Expected output: `Synced` (or `OutOfSync` if you have uncommitted changes).

## Troubleshooting

* **ArgoCD shows "repository not accessible"** -- Verify the SSH key or PAT
  has read access.  For SSH, confirm the key has no passphrase (`ssh-keygen
  -y -f ~/.ssh/ztvp-deploy-key` should not prompt).

* **Secret not found during install** -- Ensure you ran `load-secrets` (part
  of `post-install`) *after* the bootstrap secret was created.  The
  `TOKEN_SECRET` and `TOKEN_NAMESPACE` values must match exactly.

* **GitLab HTTPS fails** -- Remember that GitLab PAT auth requires
  `username: oauth2`, not your GitLab user handle.
