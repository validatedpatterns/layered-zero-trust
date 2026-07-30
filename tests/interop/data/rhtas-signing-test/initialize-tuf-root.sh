echo "Downloading TUF root..."
curl -ksSL -o /tmp/tuf-root.json https://${TUF_URL}/root.json

ls -lh /tmp

cosign initialize \
  --verbose \
  --mirror=https://${TUF_URL} \
  --root=https://${TUF_URL}/root.json \
  --root-checksum=$(sha256sum /tmp/tuf-root.json | cut -d' ' -f1)
echo "Cosign initialization returns: $?"

# ls -la ~/.sigstore/root/
