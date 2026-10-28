# Crafty

Uses the signed [Crafty provider](https://registry.terraform.io/providers/bart-kochanowicz/crafty/0.1.9)
and a separate Garage state at `prod/crafty/terraform.tfstate`.
Deploy through the [shared plan and approval workflow](../README.md#plan-and-apply).
The private automation supplies `CRAFTY_API_TOKEN`; local plans use
`TF_VAR_crafty_token`.

Houston reaches only the server API through the private Admin gateway.
The provider's verified authentication baseline is a dedicated full-access API
key belonging to an administrator. Keep the key outside Git.

Server definitions need `lifecycle { prevent_destroy = true }`: changing
installation inputs replaces the server and creates a new directory.
Existing panel servers cannot be imported. ZIP server packs must be prepared
for server use, pinned by SHA-256, and available on Houston; the provider does
not accept the Minecraft EULA or start the game.

ATM10 4.14 and 8.3 use checksum-pinned private archives at `atm10_archive_path`
and `atm10_8_3_archive_path`. Keep these on Houston's SSD under
`/srv/terraform/artifacts`, readable by `terraform-ops` (mode `0640`). They include
the saved world and server settings. Both launch commands select Java 21 and
limit the heap to 12 GiB within the shared 16 GiB container. Automatic startup
is disabled. Run only one game at a time; both use TCP30000.

ATM10 4.14 uses a native ZIP backup policy on the worker's SATA disk. The schedule
runs on Mondays at 03:00 Europe/Warsaw and keeps the four latest archives.
Crafty stops the game for each copy and restarts it only if it was running;
the panel stays up. Terraform manages the existing policy and its schedule.
The game policy covers the server directory. [K8up](../../docs/backups.md) copies
the panel database and configuration separately to Houston.
