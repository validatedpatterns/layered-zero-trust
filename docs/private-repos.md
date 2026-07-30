# Deploying from a Private Repository

This document describes how to deploy the Layered Zero Trust Validated Pattern
from a private Git repository.

The Validated Patterns framework supports deploying from both SSH-secured and
HTTPS-secured (PAT) private repositories.  The mechanism works by creating an
ArgoCD repository secret **before** the pattern is deployed, so that the VP
operator can propagate credentials to all ArgoCD instances managed by the
pattern.

> [!NOTE]
> The upstream documentation is at
> <https://validatedpatterns.io/learn/private-repos/>.  This page provides
> ZTVP-specific guidance that builds on the framework docs.

## Prerequisites

* An OpenShift 4.16+ cluster with `oc` CLI access
* A fork or private copy of this repository
* A deploy key (SSH) or Personal Access Token (HTTPS) with **read** access

> [!IMPORTANT]
> The git remote URL in your local clone **must match** the auth type in
> your `bootstrap_secrets`.  The Makefile passes the remote URL to the
> Pattern CR verbatim when `TOKEN_SECRET` is set:
>
> * SSH auth: remote must be `git@host:org/repo.git`
> * HTTPS/PAT auth: remote must be `https://host/org/repo.git`
>
> Set with: `git remote set-url origin <matching-url>`

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
cp values-secret.yaml.template ~/values-secret.yaml
```

Edit `~/values-secret.yaml` and uncomment **Option A**
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
  - name: insecureIgnoreHostKey
    value: "true"
  - name: sshPrivateKey
    path: ~/.ssh/ztvp-deploy-key
```

> [!NOTE]
> **About `insecureIgnoreHostKey`:** ArgoCD ships with pre-populated SSH
> fingerprints for github.com, gitlab.com, bitbucket.org, and
> ssh.dev.azure.com in its `argocd-ssh-known-hosts-cm` ConfigMap.  If your
> repository is hosted on one of these providers you may omit
> `insecureIgnoreHostKey` and ArgoCD will verify the host key automatically.
>
> For self-hosted Git servers (e.g. internal GitLab), the VP framework's
> `bootstrap_secrets` mechanism does not currently support injecting entries
> into `argocd-ssh-known-hosts-cm`.  Since the `vp-gitops` namespace does
> not exist until the VP operator creates it during install, you cannot
> pre-populate known hosts beforehand.  Use `insecureIgnoreHostKey: "true"`
> for the initial deployment.
>
> As a post-install hardening step, you can add proper host verification
> and remove the insecure flag:
>
> ```shell
> ssh-keyscan gitlab.internal.example.com >> /tmp/known_hosts
> oc patch cm argocd-ssh-known-hosts-cm -n vp-gitops \
>   --type merge -p "{\"data\":{\"ssh_known_hosts\":\"$(cat /tmp/known_hosts)\"}}"
> ```

### 4. Deploy

The Makefile performs a pre-flight `git ls-remote` check against the HTTPS
form of the URL.  For private repos this check will fail because the local
machine does not have credentials for the private remote.  Pass
`DISABLE_VALIDATE_ORIGIN=true` to skip it:

```shell
./pattern.sh make DISABLE_VALIDATE_ORIGIN=true \
  TOKEN_SECRET=private-repo TOKEN_NAMESPACE=openshift-operators install
```

> [!NOTE]
> This is safe -- the cluster uses the `private-repo` secret (SSH key or PAT)
> for actual access; the validation is only a local convenience check.

## Option B: HTTPS with Personal Access Token (PAT)

### 1. Create a PAT

* **GitHub:** Settings -> Developer settings -> Personal access tokens ->
  Fine-grained tokens.  Grant **Contents: Read** on the target repository.
* **GitLab:** Settings -> Access Tokens.  Grant **Reporter** role with
  `read_repository` scope (Guest role is insufficient to clone code).

Store the token in a local file:

```shell
mkdir -p ~/.config/validated-patterns
echo -n "ghp_xxxxxxxxxxxxxxxxxxxx" > ~/.config/validated-patterns/git-pat
chmod 600 ~/.config/validated-patterns/git-pat
```

### 2. Configure values-secret

Copy the template and uncomment the HTTPS `bootstrap_secrets` block:

```shell
cp values-secret.yaml.template ~/values-secret.yaml
```

Edit `~/values-secret.yaml` and uncomment **Option B**
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

For private repos the Makefile performs a pre-flight `git ls-remote` check
that will fail because the local machine does not have HTTPS credentials for
the private remote.  Pass `DISABLE_VALIDATE_ORIGIN=true` to skip it:

```shell
./pattern.sh make DISABLE_VALIDATE_ORIGIN=true \
  TOKEN_SECRET=private-repo TOKEN_NAMESPACE=openshift-operators install
```

> [!NOTE]
> This is safe -- the cluster uses the `private-repo` secret (SSH key or PAT)
> for actual access; the validation is only a local convenience check.

## How It Works

1. The `bootstrap_secrets` section in `values-secret.yaml` instructs the
   Validated Patterns framework to create the `private-repo` Kubernetes
   Secret in the `openshift-operators` namespace **before** deploying the
   pattern.

2. The `argocd.argoproj.io/secret-type: repository` label tells ArgoCD to
   pick up the secret as a repository credential.

3. The `TOKEN_SECRET` and `TOKEN_NAMESPACE` Make variables set the
   `tokenSecret` and `tokenSecretNamespace` fields on the Pattern Custom
   Resource.  The VP operator copies the secret as
   `vp-private-repo-credentials` into `vp-gitops` (its managed ArgoCD
   namespace).

4. The ACM chart (0.2.x+) `vp-private-hub-policy` copies credentials from
   `global.vpArgoNamespace`, which the VP operator automatically sets to
   `vp-gitops`.  This allows the policy to find the secret the VP operator
   placed there without any manual override.

## Verifying

After deployment, confirm the repository secret was created:

```shell
oc get secret private-repo -n openshift-operators \
  -o jsonpath='{.metadata.labels.argocd\.argoproj\.io/secret-type}'
```

Expected output: `repository`

Confirm the VP operator propagated the credential to `vp-gitops`:

```shell
oc get secret vp-private-repo-credentials -n vp-gitops \
  -o jsonpath='{.metadata.labels.argocd\.argoproj\.io/secret-type}'
```

Expected output: `repository`

Check the Cluster ArgoCD can see the repository:

```shell
oc get application layered-zero-trust-hub -n vp-gitops \
  -o jsonpath='{.status.sync.status}'
```

Expected output: `Synced` (or `OutOfSync` if you have uncommitted changes).

## Troubleshooting

* **ACM shows Degraded (vp-private-hub-policy NonCompliant)** -- The ACM
  chart 0.1.x has `openshift-gitops` hardcoded in the private-repo policy
  template, but the VP operator (0.0.70+) places credentials in
  `vp-gitops`.  Ensure `values-hub.yaml` uses ACM chart 0.2.x or later
  (`chartVersion: 0.2.*`), which reads `global.vpArgoNamespace` -- a value
  the VP operator sets automatically.

* **ArgoCD shows "repository not accessible"** -- Verify the SSH key or PAT
  has read access.  For SSH, confirm the key has no passphrase (`ssh-keygen
  -y -f ~/.ssh/ztvp-deploy-key` should not prompt).

* **SSH: "knownhosts: key is unknown"** -- The `insecureIgnoreHostKey: "true"`
  field is missing from the bootstrap secret.  The ArgoCD repo-server runs
  in a container without your Git host's fingerprint in known_hosts.

* **HTTPS: "x509: certificate signed by unknown authority"** -- This
  affects internal/self-hosted Git servers (e.g. Gitea, GitLab) whose TLS
  certificates are signed by a custom or corporate CA.  GitHub and public
  GitLab (`gitlab.com`) use publicly trusted CAs and do not require this
  step.

  The corporate CA must be in the cluster trust store **before** install
  because the VP operator needs it to clone the repository.  Add the internal CA
  as a pre-install step:

```shell
oc create configmap custom-ca -n openshift-config \
  --from-file=ca-bundle.crt=/path/to/corporate-ca-bundle.pem
oc patch proxy/cluster --type=merge \
  -p '{"spec":{"trustedCA":{"name":"custom-ca"}}}'
```

  Wait a few minutes for operator pods to restart with the updated bundle.

  If the custom CA is added **after** the pattern is already deployed, the
  `trusted-ca-bundle` ConfigMap will be updated by the cluster CA injector,
  but the ArgoCD repo-server will **not** pick it up automatically.  The
  repo-server uses an init container (`fetch-ca`) that copies the CA bundle
  into an `emptyDir` volume at pod startup; this only runs once.  Restart
  the repo-server to load the updated bundle:

```shell
oc rollout restart deployment/vp-gitops-repo-server -n vp-gitops
oc rollout status  deployment/vp-gitops-repo-server -n vp-gitops
```

  > [!NOTE]
  > After the pattern deploys, the `ztvp-certificates` chart automatically
  > merges your `custom-ca` content into its managed `ztvp-proxy-ca`
  > ConfigMap and switches `proxy/cluster.spec.trustedCA` to
  > `ztvp-proxy-ca`.  This adds the cluster ingress and service CAs so
  > that workloads like ACS Central can reach Keycloak without additional
  > manual steps.  You do **not** need to manually add the ingress CA to
  > your `custom-ca`.

* **Secret not found during install** -- Ensure you ran
  `./pattern.sh make load-secrets` *after* the bootstrap secret was created.
  The `TOKEN_SECRET` and `TOKEN_NAMESPACE` values must match exactly.

* **GitLab HTTPS fails** -- Remember that GitLab PAT auth requires
  `username: oauth2`, not your GitLab user handle.
