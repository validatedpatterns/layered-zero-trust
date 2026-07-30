cat /tmp/test.bundle | jq .

# View certificate (note: field is lowercase "cert")
cat /tmp/test.bundle | jq -r .cert | base64 -d | openssl x509 -noout -text | grep -A 2 "Subject Alternative Name"