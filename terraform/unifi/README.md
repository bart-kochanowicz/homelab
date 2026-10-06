# UniFi Terraform

`ubiquiti-community/unifi` 0.57.0 manages LAN configuration through
[`../modules/unifi`](../modules/unifi). Garage stores state at
`prod/unifi/terraform.tfstate`; [R2 snapshots](../R2_BACKUP.md) use `backups/prod/unifi/`.
LAN resources come from the `networks` input; an empty map manages none.

The private [Apply production Terraform workflow](https://github.com/bart-kochanowicz/homelab-automation/actions/workflows/terraform-apply.yaml)
runs on Houston through its locked `/usr/local/bin/terraform`.
Select `terraform_root=unifi` and `operation=plan` or `apply`, using the current
`homelab/main` SHA and its successful Validate push run ID.

`UNIFI_AUTH` is an Actions secret containing local credentials or an API key.
The job supplies it as ephemeral `TF_VAR_unifi_auth`. `UNIFI_CONTROLLER` and
`UNIFI_CA_CERT_PEM` are repository variables. The controller hostname resolves
on Houston and matches the certificate SAN; TLS verification is enabled.
See [automation configuration](https://github.com/bart-kochanowicz/homelab-automation#github-configuration).

Public CI uses backend-disabled validation and mock providers without credentials.
