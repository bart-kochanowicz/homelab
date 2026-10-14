variable "site" {
  description = "UniFi Network site managed by the module."
  type        = string
  nullable    = false
}

variable "name" {
  description = "WireGuard server name."
  type        = string
  nullable    = false
}

variable "subnet" {
  description = "Private IPv4 network CIDR; the server uses its first host address."
  type        = string
  nullable    = false

  validation {
    condition = try(
      can(cidrnetmask(var.subnet)) &&
      split("/", var.subnet)[0] == cidrhost(var.subnet, 0) &&
      tonumber(split("/", var.subnet)[1]) <= 29 &&
      anytrue([for block in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"] :
        cidrhost("${cidrhost(var.subnet, 0)}/${split("/", block)[1]}", 0) == cidrhost(block, 0) &&
        tonumber(split("/", var.subnet)[1]) >= tonumber(split("/", block)[1])
      ]), false
    )
    error_message = "Use a canonical RFC1918 IPv4 network CIDR with a prefix no longer than /29."
  }

  validation {
    condition = alltrue([for reserved in var.reserved_subnets : try(
      cidrhost("${cidrhost(var.subnet, 0)}/${split("/", reserved)[1]}", 0) != cidrhost(reserved, 0) &&
      cidrhost("${cidrhost(reserved, 0)}/${split("/", var.subnet)[1]}", 0) != cidrhost(var.subnet, 0), false
    )])
    error_message = "The VPN subnet must not overlap reserved networks."
  }
}

variable "reserved_subnets" {
  description = "IPv4 LAN, cluster and other networks excluded from the VPN pool."
  type        = set(string)
  default     = []
  nullable    = false

  validation {
    condition     = alltrue([for subnet in var.reserved_subnets : can(cidrnetmask(subnet))])
    error_message = "Reserved networks must be valid IPv4 CIDRs."
  }
}

variable "public_ip" {
  description = "Fixed public IPv4 address on WAN1 and the client endpoint."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition = try(can(cidrnetmask("${var.public_ip}/32")) && alltrue([
      for block in [
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4"
      ] : cidrhost("${var.public_ip}/${split("/", block)[1]}", 0) != cidrhost(block, 0)
    ]), false)
    error_message = "The WAN endpoint must be a public unicast IPv4 address."
  }
}

variable "port" {
  description = "WireGuard UDP listening port."
  type        = number
  default     = 51820
  nullable    = false

  validation {
    condition     = var.port >= 1 && var.port <= 65535 && floor(var.port) == var.port
    error_message = "The UDP port must be an integer from 1 to 65535."
  }
}

variable "dns_servers" {
  description = "One or two IPv4 DNS servers for clients."
  type        = list(string)
  nullable    = false

  validation {
    condition = length(var.dns_servers) >= 1 && length(var.dns_servers) <= 2 && alltrue([
      for ip in var.dns_servers : can(cidrnetmask("${ip}/32"))
    ])
    error_message = "Provider 0.57.0 supports one or two IPv4 DNS servers."
  }
}

variable "peers" {
  description = "Devices keyed by stable names; only public keys and unique tunnel addresses."
  type = map(object({
    public_key   = string
    interface_ip = string
  }))
  default  = {}
  nullable = false

  validation {
    condition = alltrue([for key, peer in var.peers :
      can(regex("^[a-z][a-z0-9-]*$", key)) &&
      can(regex("^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$", peer.public_key)) &&
      peer.public_key != "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    ])
    error_message = "Use stable lowercase device names and non-zero 32-byte base64 public keys."
  }

  validation {
    condition = alltrue([for peer in values(var.peers) : try(
      can(cidrnetmask("${peer.interface_ip}/32")) &&
      cidrhost("${peer.interface_ip}/${split("/", var.subnet)[1]}", 0) == cidrhost(var.subnet, 0) &&
      !contains([cidrhost(var.subnet, 0), cidrhost(var.subnet, 1), cidrhost(var.subnet, -1)], peer.interface_ip), false
    )])
    error_message = "Peer addresses must be usable IPv4 hosts in the VPN subnet and exclude the server address."
  }

  validation {
    condition = (
      length(distinct([for peer in values(var.peers) : peer.interface_ip])) == length(var.peers) &&
      length(distinct([for peer in values(var.peers) : peer.public_key])) == length(var.peers)
    )
    error_message = "Every peer must have its own tunnel address and public key."
  }
}
