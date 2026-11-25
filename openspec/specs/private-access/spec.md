# private-access Specification

## Purpose
Every homelab endpoint stays on private networks. Clients reach applications
only through UniFi private DNS and the Envoy private gateways, from the VLANs
and VPN that each gateway allows.

## Requirements
### Requirement: No public exposure
Application endpoints SHALL have no public DNS record, Cloudflare Tunnel route
or WAN port forward.

#### Scenario: Public request
- **WHEN** a client on the internet resolves or connects to an application hostname
- **THEN** no public record or forwarded port leads to the cluster

#### Scenario: New application
- **WHEN** a change adds an application hostname
- **THEN** the hostname is a UniFi private DNS record under `thecavespace.net`
- **AND** Cloudflare DNS gains no record for it

### Requirement: Gateway source restrictions
The Home gateway SHALL accept clients from the Home, Admin and WireGuard
networks. The Admin gateway SHALL accept clients from the Admin and WireGuard
networks, plus the narrow exceptions its SecurityPolicy names.

#### Scenario: IoT client opens an admin panel
- **WHEN** a client on the IoT VLAN requests an Admin gateway hostname
- **THEN** the gateway denies the request

#### Scenario: Houston calls the Crafty API
- **WHEN** Houston requests a path under `/api/v2/servers` on the Crafty hostname
- **THEN** the gateway allows it, and denies Houston every other path and hostname

### Requirement: Default-deny pod networking
Each application namespace whose workloads accept connections SHALL deny
ingress and egress by default and allow only the ports and peers its workload
needs.

#### Scenario: Unlisted peer
- **WHEN** a pod connects to an application port that no policy allows for it
- **THEN** Cilium drops the connection

### Requirement: Encrypted backends
Gateways SHALL terminate TLS with cert-manager certificates and connect to
backends over verified TLS where the backend supports it.

#### Scenario: Backend certificate rotation
- **WHEN** cert-manager renews a backend certificate
- **THEN** the gateway keeps verifying the backend without a manual change
