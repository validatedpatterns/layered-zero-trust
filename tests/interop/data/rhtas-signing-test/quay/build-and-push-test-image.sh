#!/bin/bash

# Create a test directory
mkdir -p /tmp/quay-test-app
cd /tmp/quay-test-app

# Create a simple Dockerfile
cat > Dockerfile <<EOF
FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
RUN microdnf install -y nginx && microdnf clean all
COPY index.html /usr/share/nginx/html/
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
EOF

# Create a simple HTML file
cat > index.html <<EOF
<!DOCTYPE html>
<html>
<head><title>Signed Test App</title></head>
<body>
<h1>This container image is signed with RHTAS!</h1>
<p>Built on: $(date)</p>
</body>
</html>
EOF

# Build the image
podman build -t test-app:v1 .

# Verify the image
podman images | grep test-app

# Tag the image for Quay registry
# Namespace is either the username (e.g., quayadmin) or an organization (e.g., developer1)

# If using organization 'developer1':
export QUAY_NAMESPACE="developer1"
# If using your user 'quayadmin':
# export QUAY_NAMESPACE="quayadmin"

export QUAY_IMAGE="${QUAY_URL}/${QUAY_NAMESPACE}/test-app:v1"
podman tag test-app:v1 ${QUAY_IMAGE}

echo "Tagged image: ${QUAY_IMAGE}"

# Push the image
podman push ${QUAY_IMAGE}