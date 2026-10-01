# Terraform Backend Configuration

This directory contains backend configuration for Terraform state management.

## 🔒 Security Notice

**`backend.tf` is gitignored** to keep your Terraform Cloud organization and workspace names private.

## 🚀 Setup Options

1. **Create backend.tf from example:**
   ```bash
   cp backend.tf.example backend.tf
   ```

2. **Edit backend.tf with your details:**
   ```hcl
   terraform {
     cloud {
       organization = "your-org-name"
       workspaces {
         name = "homelab-cloudflare"
       }
     }
   }
   ```

3. **Login to Terraform Cloud:**
   ```bash
   terraform login
   ```

4. **Initialize and migrate state:**
   ```bash
   terraform init
   # Answer "yes" to migrate existing state
   ```



## Garage compatibility gate

Garage 2.4.1 is installed on Houston, but it is not approved as the primary
Terraform backend with native S3 state locking. Its [versioned known issues](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/doc/book/reference-manual/known-issues.md)
explicitly rule out safe conditional writes for mutual exclusion. Terraform
1.16.4 [creates its lock with `If-None-Match: *`](https://github.com/hashicorp/terraform/blob/v1.16.4/internal/backend/remote-state/s3/client.go).
A working bucket and successful state upload would not verify that locking works.

`../scripts/check-garage-locking.sh` probes that prerequisite on Houston:
it writes a uniquely named disposable object under
`terraform-state/compatibility-checks/locking/`, tries to overwrite it with
another conditional PUT, and expects HTTP 412. It then deletes only its probe
object. It never reads or modifies an existing Terraform state or lock file.
A failed probe exits nonzero. Even a successful sequential check does not
prove atomic behavior under concurrent writes; review the backend's documented
guarantees before adopting it.

The probe needs curl with `--aws-sigv4` and Garage credentials in environment
variables. It accepts `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` or the
`GARAGE_DEFAULT_ACCESS_KEY` / `GARAGE_DEFAULT_SECRET_KEY` names from the
root-only bootstrap file. It defaults to `http://127.0.0.1:3900`; an override
through `GARAGE_S3_ENDPOINT` must also be a loopback HTTP endpoint.
Credentials are passed to curl over stdin and are not printed. Disable shell
tracing when handling them.

Run the probe after loading credentials into a temporary shell environment.
Do not copy the credentials into Git or paste them into chat. No Ansible apply
or backend migration is part of this check. The current backend remains in
use until a compatible locking design is selected.

Local response files are private and removed on exit. If remote cleanup fails,
the script reports the exact disposable key for manual removal. Removing the
probe script does not change Garage, its bucket, or the configured backend.
