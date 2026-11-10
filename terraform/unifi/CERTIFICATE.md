# UniFi console certificate

`https://unifi.thecavespace.net` resolves privately to `10.0.80.1`. The router
serves a publicly trusted Let's Encrypt certificate, independently of Kubernetes.
Browsers and Terraform use their system CA stores; keep TLS verification enabled.

## Native issuance and renewal

In UniFi Control Plane → Console → Certificates, configure automatic Let's
Encrypt for `unifi.thecavespace.net` using Cloudflare DNS-01. Use a dedicated
API token with DNS Edit and Zone Read scoped to `thecavespace.net`. Keep the
token and certificate private key on the router; do not commit or log them.
Manual TXT validation does not provide unattended renewal.

UniFi owns temporary `_acme-challenge.unifi.thecavespace.net` TXT records.
Do not manage them with Terraform or create public A/AAAA records, port
forwarding, or a Cloudflare Tunnel. Check native certificate status for renewal
failures and expiry. Retain the factory certificate for console recovery.

## Verify access

From Admin or administrative WireGuard, using UniFi DNS:

```bash
dig @10.0.80.1 unifi.thecavespace.net A +short
curl --fail --head https://unifi.thecavespace.net
```

Require `10.0.80.1` and successful HTTPS without certificate exceptions. Verify
the same HTTPS endpoint from Houston before running Actions. The private
automation repository's `UNIFI_CONTROLLER` must use this hostname and its
workflow must use the system CA store rather than pinning a leaf certificate.
Renewals must not require changes to Keychain or Actions variables.
