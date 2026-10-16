variable "site" {
  description = "UniFi Network site managed by the module."
  type        = string
  nullable    = false
}

variable "networks" {
  description = "DHCP networks used to validate reserved addresses; VLAN membership is managed separately."
  type = map(object({
    subnet = string
    dhcp = object({
      start = string
      stop  = string
    })
  }))
  nullable = false
}

variable "reservations" {
  description = "MAC-to-IPv4 reservations keyed by public logical name; import existing clients before applying."
  type = map(object({
    mac     = string
    ip      = string
    network = string
  }))
  nullable = false

  validation {
    condition = (
      alltrue([for name, reservation in var.reservations :
        can(regex("^[a-z][a-z0-9-]*$", name)) &&
        can(regex("(?i)^([0-9a-f]{2}:){5}[0-9a-f]{2}$", reservation.mac))
      ]) &&
      length(distinct([for reservation in values(var.reservations) : lower(reservation.mac)])) == length(var.reservations) &&
      length(distinct([for reservation in values(var.reservations) : reservation.ip])) == length(var.reservations)
    )
    error_message = "Reservations require logical names, valid unique MACs and distinct IPv4 addresses."
  }

  validation {
    condition = alltrue([
      for reservation in values(var.reservations) : try(
        can(cidrnetmask("${reservation.ip}/32")) &&
        cidrhost("${reservation.ip}/${split("/", var.networks[reservation.network].subnet)[1]}", 0) == cidrhost(var.networks[reservation.network].subnet, 0) &&
        !contains([
          cidrhost(var.networks[reservation.network].subnet, 0),
          cidrhost(var.networks[reservation.network].subnet, -1),
          split("/", var.networks[reservation.network].subnet)[0]
        ], reservation.ip) &&
        !(
          sum([for i, octet in split(".", reservation.ip) : tonumber(octet) * pow(256, 3 - i)]) >=
          sum([for i, octet in split(".", var.networks[reservation.network].dhcp.start) : tonumber(octet) * pow(256, 3 - i)]) &&
          sum([for i, octet in split(".", reservation.ip) : tonumber(octet) * pow(256, 3 - i)]) <=
          sum([for i, octet in split(".", var.networks[reservation.network].dhcp.stop) : tonumber(octet) * pow(256, 3 - i)])
        ), false
      )
    ])
    error_message = "Reserved IPv4 addresses must belong to a declared DHCP LAN and exclude its gateway, network, broadcast and dynamic pool."
  }
}
