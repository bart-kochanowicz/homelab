# Local controller certificate

Run commands from the repository root on macOS after preparing the private
UniFi inputs in [the local plan guide](../LOCAL_PLAN.md#unifi).

The gateway generates its certificate; the Mac needs only the public certificate,
not a new certificate or the gateway's private key. For an enrolled controller,
download the approved certificate from the private automation repository:

```bash
gh api repos/bart-kochanowicz/homelab-automation/actions/variables/UNIFI_CA_CERT_PEM \
  --jq '.value' > .secrets/unifi/controller-certificate.pem
openssl x509 -in .secrets/unifi/controller-certificate.pem -noout -fingerprint -sha256 -dates
openssl x509 -in .secrets/unifi/controller-certificate.pem -noout -text
```

The repository variable is the approved certificate record. Check validity dates
and the `localhost` subject alternative name required by the local tunnel.

For first enrollment or a certificate replacement, obtain a candidate from the
controller through Houston:

```bash
mkdir -p .cache
ssh houston-01 'openssl s_client -connect 192.168.1.1:443 -servername unifi.local </dev/null 2>/dev/null' \
  | openssl x509 -outform PEM -out .cache/unifi-controller-candidate.pem
openssl x509 -in .cache/unifi-controller-candidate.pem -noout -fingerprint -sha256 -dates
openssl x509 -in .cache/unifi-controller-candidate.pem -noout -text
```

Verify its SHA-256 fingerprint through the console certificate viewer over a
trusted administration connection or a trusted certificate backup. Check dates
and the `localhost` SAN; successful download alone does not establish trust.
After verification, register this public certificate for Actions and the Mac:

```bash
gh variable set UNIFI_CA_CERT_PEM --repo bart-kochanowicz/homelab-automation \
  < .cache/unifi-controller-candidate.pem
cp .cache/unifi-controller-candidate.pem .secrets/unifi/controller-certificate.pem
```

On macOS, the provider uses Keychain for certificate trust. Add the approved
certificate for SSL to `localhost`, authorizing the macOS prompt if requested:

```bash
security add-trusted-cert -r trustRoot -p ssl -s localhost \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  .secrets/unifi/controller-certificate.pem
security verify-cert -c .secrets/unifi/controller-certificate.pem -p ssl -s localhost
```

Verification must succeed before planning. Repeat enrollment and update Actions
and Keychain trust when the gateway certificate changes or expires.
