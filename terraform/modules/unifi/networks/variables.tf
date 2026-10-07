variable "site" {
  description = "UniFi Network site managed by the module."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9_-]*$", var.site))
    error_message = "The site must be a non-empty lowercase UniFi site name."
  }
}

variable "name_prefix" {
  description = "Prefix for generated names; explicit network names override it."
  type        = string
  default     = "cavespace-"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*-$", var.name_prefix))
    error_message = "The prefix must use lowercase letters, digits or hyphens and end with a hyphen."
  }
}

variable "networks" {
  description = "LAN networks keyed by stable identifiers, with gateway CIDRs and optional DHCP pools."
  type = map(object({
    name   = optional(string)
    vlan   = optional(number)
    subnet = string
    dhcp = optional(object({
      start     = string
      stop      = string
      leasetime = optional(string, "24h")
    }))
  }))
  default  = {}
  nullable = false

  validation {
    condition = alltrue([
      for key, network in var.networks : key != "default" && network.name != "Default"
    ])
    error_message = "The built-in Default LAN is read-only; reserve its name and logical key."
  }

  validation {
    condition = alltrue(flatten([
      for network in values(var.networks) : [
        for reserved in var.reserved_subnets : try(
          cidrhost("${cidrhost(network.subnet, 0)}/${split("/", reserved)[1]}", 0) != cidrhost(reserved, 0) &&
          cidrhost("${cidrhost(reserved, 0)}/${split("/", network.subnet)[1]}", 0) != cidrhost(network.subnet, 0), false
        )
      ]
    ]))
    error_message = "Managed LAN subnets must not overlap reserved LANs."
  }

  validation {
    condition = alltrue([
      for key, network in var.networks :
      can(regex("^[a-z][a-z0-9_-]*$", key)) &&
      (network.name == null ? true : length(trimspace(network.name)) > 0)
    ])
    error_message = "Use non-empty logical keys and non-empty explicit names."
  }

  validation {
    condition = alltrue([
      for network in values(var.networks) : network.vlan == null ? true :
      network.vlan >= 1 && network.vlan <= 4094 && floor(network.vlan) == network.vlan && network.vlan != 35
    ])
    error_message = "LAN VLANs must be integers from 1 to 4094; VLAN 35 is reserved for the WAN."
  }

  validation {
    condition = (
      length(distinct([for network in values(var.networks) : network.vlan if network.vlan != null])) ==
      length([for network in values(var.networks) : network.vlan if network.vlan != null]) &&
      length([for network in values(var.networks) : network if network.vlan == null]) <= 1
    )
    error_message = "VLAN IDs must be unique; at most one LAN can be untagged."
  }

  validation {
    condition = alltrue([
      for network in values(var.networks) : try(
        can(cidrnetmask(network.subnet)) &&
        split("/", network.subnet)[0] != cidrhost(network.subnet, 0) &&
        split("/", network.subnet)[0] != cidrhost(network.subnet, -1) &&
        (
          (startswith(cidrhost(network.subnet, 0), "10.") && tonumber(split("/", network.subnet)[1]) >= 8) ||
          (startswith(cidrhost(network.subnet, 0), "192.168.") && tonumber(split("/", network.subnet)[1]) >= 16) ||
          (split(".", cidrhost(network.subnet, 0))[0] == "172" &&
            tonumber(split(".", cidrhost(network.subnet, 0))[1]) >= 16 &&
            tonumber(split(".", cidrhost(network.subnet, 0))[1]) <= 31 &&
          tonumber(split("/", network.subnet)[1]) >= 12)
        ), false
      )
    ])
    error_message = "Each subnet must contain a usable gateway address in a private IPv4 CIDR."
  }

  validation {
    # Ordered pairs detect containment at either network's prefix length.
    condition = alltrue(flatten([
      for key, network in var.networks : [
        for other_key, other in var.networks : key == other_key ? true : try(
          cidrhost("${cidrhost(network.subnet, 0)}/${split("/", other.subnet)[1]}", 0) != cidrhost(other.subnet, 0), false
        )
      ]
    ]))
    error_message = "LAN subnets must not overlap."
  }

  validation {
    condition = alltrue([
      for network in values(var.networks) : network.dhcp == null ? true : try(
        cidrhost("${network.dhcp.start}/${split("/", network.subnet)[1]}", 0) == cidrhost(network.subnet, 0) &&
        cidrhost("${network.dhcp.stop}/${split("/", network.subnet)[1]}", 0) == cidrhost(network.subnet, 0) &&
        network.dhcp.start != cidrhost(network.subnet, 0) &&
        network.dhcp.stop != cidrhost(network.subnet, -1),
        false
      )
    ])
    error_message = "DHCP pool endpoints must be usable IPv4 addresses inside their LAN subnet."
  }

  validation {
    condition = alltrue([
      for network in values(var.networks) : network.dhcp == null ? true : try(
        # Numeric IPv4 comparisons avoid lexicographic address ordering.
        sum([for i, octet in split(".", network.dhcp.start) : tonumber(octet) * pow(256, 3 - i)]) <=
        sum([for i, octet in split(".", network.dhcp.stop) : tonumber(octet) * pow(256, 3 - i)]) &&
        !(
          sum([for i, octet in split(".", network.dhcp.start) : tonumber(octet) * pow(256, 3 - i)]) <=
          sum([for i, octet in split(".", split("/", network.subnet)[0]) : tonumber(octet) * pow(256, 3 - i)]) &&
          sum([for i, octet in split(".", split("/", network.subnet)[0]) : tonumber(octet) * pow(256, 3 - i)]) <=
          sum([for i, octet in split(".", network.dhcp.stop) : tonumber(octet) * pow(256, 3 - i)])
        ), false
      )
    ])
    error_message = "DHCP pools must be ordered and exclude the gateway address."
  }
}

variable "reserved_subnets" {
  description = "Read-only IPv4 LAN subnets excluded from managed addressing."
  type        = set(string)
  default     = []
  nullable    = false

  validation {
    condition     = alltrue([for subnet in var.reserved_subnets : can(cidrnetmask(subnet))])
    error_message = "Reserved LANs must have valid IPv4 subnets."
  }
}

variable "vlan_only_networks" {
  description = "Unrouted networks keyed by logical identifier, with no gateway or DHCP."
  type        = map(number)
  default     = {}
  nullable    = false

  validation {
    condition = alltrue([
      for key, vlan in var.vlan_only_networks :
      can(regex("^[a-z][a-z0-9_-]*$", key)) && key != "default" &&
      !contains(keys(var.networks), key) &&
      vlan >= 1 && vlan <= 4094 && floor(vlan) == vlan && vlan != 35 &&
      !contains([for network in values(var.networks) : network.vlan], vlan)
    ]) && length(distinct(values(var.vlan_only_networks))) == length(var.vlan_only_networks)
    error_message = "Unrouted LAN keys and VLANs must be unique and must not conflict with routed LANs or WAN VLAN 35."
  }
}
