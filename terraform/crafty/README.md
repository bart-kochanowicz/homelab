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

ATM10 uses native ZIP backup policies on the worker's SATA disk. Schedules use
Europe/Warsaw: daily at 03:00, Sunday at 04:00 and the first day of each month at
05:00, retaining 7/4/3 archives respectively. Crafty stops the game for each copy
and restarts it only if it was running. The panel stays up. Policy IDs refer to
existing Crafty policies; Terraform manages their settings and schedules.
These backups cover the game directory, not the panel database or configuration.
