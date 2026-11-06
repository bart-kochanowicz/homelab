# Crafty

Uses the signed [Crafty provider](https://registry.terraform.io/providers/bart-kochanowicz/crafty/0.1.10)
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

ATM10 4.14 and the active ATM10 server use checksum-pinned creation archives at
`atm10_archive_path` and `atm10_8_3_archive_path`. Keep these on Houston's SSD under
`/srv/terraform/artifacts`, readable by `terraform-ops` (mode `0640`). They include
the saved world and server settings. Both launch commands select Java 21.
The active server runs ATM10 8.5 with NeoForge 21.1.265 and Astral Sorcery 2.0.3.59.
Its resource address, output key and creation inputs retain the original 8.3
identity. The provider uses the archive and executable only for initial import;
changing them replaces the server. Pack files are updated separately while the
game is stopped, preserving `world`, root-level `DIM_*` data and server settings.
Keep the existing ID, backup policy and log mount when updating the pack.
The active server enables `manage_memory` for in-place heap updates and drift
detection.
Its memory inputs and JVM flags share the same locals: 4/20 units mean
4000/20000 MiB (1000 MiB per unit, approximately 19.53 GiB maximum heap).
ATM10 4.14 keeps a 12 GiB maximum heap and creation-only memory inputs. The shared
container reserves 4 GiB of memory and 1 CPU, with limits of 24 GiB and 5 CPUs.
Memory above the request depends on available node capacity during gameplay.
Keep at least 4 GiB outside the active game's maximum heap for native allocations
and Crafty. Automatic startup is disabled. Run only one game at a time; both use
TCP30000. Apply the container memory increase before raising the game heap;
changing the Deployment restarts Crafty, and the game needs a manual start.

The active ATM10 server uses a native ZIP backup policy on the worker's SATA disk.
The schedule runs on Mondays at 03:00 Europe/Warsaw and keeps the four latest archives.
Crafty stops the game for each copy and restarts it only if it was running;
the panel stays up. Terraform manages the existing policy and its schedule.
The game policy covers the server directory. [K8up](../../docs/backups.md) copies
only the panel's `app-config/` directory, including `db/crafty.sqlite`, separately
to Houston. The game ZIPs stay on the worker; neither copy has configured offsite
replication. Recovery needs both the panel configuration and matching game files;
use the backup guide's isolated restore instructions before in-place recovery.
