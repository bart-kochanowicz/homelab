# UniFi Terraform

`ubiquiti-community/unifi` 0.57.0 manages LAN configuration through
[`../modules/unifi`](../modules/unifi). Garage stores state at
`prod/unifi/terraform.tfstate`; [R2 snapshots](../R2_BACKUP.md) use `backups/prod/unifi/`.

Operations run manually on Houston through [`terraform-unifi.sh`](../../scripts/terraform-unifi.sh)
and its shared Terraform lock. Public CI uses backend-disabled validation and mock providers.

Private inputs follow [`variables.tfvars.json.example`](variables.tfvars.json.example).
`UNIFI_INPUT_FILE` defaults to `.secrets/unifi/variables.tfvars.json` in the checkout.
Files are operator-owned `0600` in a `0700` directory. Garage credentials use
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. UniFi authentication is ephemeral.

`UNIFI_CA_CERT_FILE` defaults to `controller-certificate.pem` beside the inputs.
The controller hostname resolves on Houston and matches the certificate SAN.
TLS verification is enabled; provider environment overrides and debug logs are cleared.

From the checkout root with private inputs and Garage credentials loaded:

```bash
./scripts/terraform-unifi.sh init
./scripts/terraform-unifi.sh plan -input=false -out=../../.secrets/unifi/network.tfplan
./scripts/terraform-unifi.sh apply ../../.secrets/unifi/network.tfplan
./scripts/backup-terraform-state.sh terraform/unifi prod/unifi
```
