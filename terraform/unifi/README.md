# UniFi Terraform

`ubiquiti-community/unifi` 0.57.0 manages LAN configuration through
[`../modules/unifi`](../modules/unifi). Garage stores state at
`prod/unifi/terraform.tfstate`; [R2 snapshots](../R2_BACKUP.md) use `backups/prod/unifi/`.

Operations run manually on Houston through `/usr/local/bin/terraform`, using its
shared lock. Public CI uses backend-disabled validation and mock providers.

Private inputs follow [`variables.tfvars.json.example`](variables.tfvars.json.example).
Store them in `.secrets/unifi/variables.tfvars.json` in the checkout.
Files are operator-owned `0600` in a `0700` directory. Garage credentials use
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. UniFi authentication is ephemeral.

The trusted certificate is `.secrets/unifi/controller-certificate.pem`.
The controller hostname resolves on Houston and matches the certificate SAN.
Use a clean environment without `UNIFI_*`, `TF_VAR_*`, `TF_CLI_ARGS*` or `TF_LOG*` overrides.

From the checkout root with private inputs and Garage credentials loaded:

```bash
set +x
umask 077
export SSL_CERT_FILE="$PWD/.secrets/unifi/controller-certificate.pem"
export TF_WORKSPACE=default
/usr/local/bin/terraform -chdir=terraform/unifi init -input=false -lockfile=readonly \
  -backend-config=../garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform/unifi plan -input=false \
  -var-file=../../.secrets/unifi/variables.tfvars.json -out=../../.secrets/unifi/network.tfplan
/usr/local/bin/terraform -chdir=terraform/unifi apply \
  -var-file=../../.secrets/unifi/variables.tfvars.json ../../.secrets/unifi/network.tfplan
./scripts/backup-terraform-state.sh terraform/unifi prod/unifi
```
