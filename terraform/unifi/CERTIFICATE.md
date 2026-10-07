# UniFi certificate on macOS

Run from the repository root after [local setup](../LOCAL_PLAN.md#one-time-setup).
Install GitHub CLI and OpenSSL; `gh auth login` needs private automation
repository access. The gateway generates the certificate; never copy its private key.

## Download the approved certificate

```bash
gh api repos/bart-kochanowicz/homelab-automation/actions/variables/UNIFI_CA_CERT_PEM \
  --jq '.value' > .secrets/unifi/controller-certificate.pem
openssl x509 -in .secrets/unifi/controller-certificate.pem -noout -fingerprint -sha256 -dates
openssl x509 -in .secrets/unifi/controller-certificate.pem -noout -text
```

Check validity dates and the `localhost` SAN used by the tunnel.

## First enrollment or replacement

```bash
mkdir -p .cache
ssh houston-01 'openssl s_client -connect 192.168.1.1:443 -servername unifi.local </dev/null 2>/dev/null' \
  | openssl x509 -outform PEM -out .cache/unifi-controller-candidate.pem
openssl x509 -in .cache/unifi-controller-candidate.pem -noout -fingerprint -sha256 -dates
openssl x509 -in .cache/unifi-controller-candidate.pem -noout -text
```

Verify SHA256 against the console certificate viewer over a trusted administration
connection or a trusted backup; download alone does not establish trust.
Check dates and the `localhost` SAN, then register the verified public certificate:

```bash
gh variable set UNIFI_CA_CERT_PEM --repo bart-kochanowicz/homelab-automation \
  < .cache/unifi-controller-candidate.pem
cp .cache/unifi-controller-candidate.pem .secrets/unifi/controller-certificate.pem
```

## Trust in Keychain

Authorize the macOS prompt; verification must succeed before planning.
Repeat enrollment and trust when the gateway certificate changes or expires.

```bash
security add-trusted-cert -r trustRoot -p ssl -s localhost \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  .secrets/unifi/controller-certificate.pem
security verify-cert -c .secrets/unifi/controller-certificate.pem -p ssl -s localhost
```
