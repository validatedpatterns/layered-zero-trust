dnf install -y jq

# Download cosign from cli-server (gzipped)
echo 'Downloading cosign from RHTAS cli-server...'
curl -skL https://${CLI_SERVER_URL}/clients/linux/cosign-amd64.gz -o /tmp/cosign-amd64.gz

# Extract the gzipped binary
echo 'Extracting cosign...'
gunzip /tmp/cosign-amd64.gz

# Install cosign
mv /tmp/cosign-amd64 /usr/local/bin/cosign
chmod +x /usr/local/bin/cosign

# Verify installation
cosign version
