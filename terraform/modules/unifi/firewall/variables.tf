variable "site" {
  description = "UniFi Network site managed by the module."
  type        = string
  nullable    = false
}

variable "name_prefix" {
  description = "Prefix for managed zones and policies."
  type        = string
  default     = "cavespace-"
  nullable    = false
}

variable "zone_network_ids" {
  description = "Custom zones and their exclusively owned network memberships."
  type        = map(set(string))
  nullable    = false

  validation {
    condition = (
      length(setintersection(toset(keys(var.zone_network_ids)), toset(keys(var.builtin_zone_ids)))) == 0 &&
      alltrue([for networks in values(var.zone_network_ids) : length(networks) > 0]) &&
      length(distinct(flatten([for networks in values(var.zone_network_ids) : tolist(networks)]))) ==
      length(flatten([for networks in values(var.zone_network_ids) : tolist(networks)]))
    )
    error_message = "Custom zones must be non-empty, distinct from built-in zones, and own each network only once."
  }
}

variable "builtin_zone_ids" {
  description = "Read-only built-in zone IDs keyed by logical name."
  type        = map(string)
  nullable    = false

  validation {
    condition = (
      length(distinct(values(var.builtin_zone_ids))) == length(var.builtin_zone_ids) &&
      alltrue([for id in values(var.builtin_zone_ids) : length(trimspace(id)) > 0])
    )
    error_message = "Built-in zone IDs must be distinct and non-empty."
  }
}

variable "builtin_policy_index" {
  description = "First controller built-in policy index; custom denies must precede it."
  type        = number
  default     = 30000
  nullable    = false

  validation {
    condition     = var.builtin_policy_index > 0 && floor(var.builtin_policy_index) == var.builtin_policy_index
    error_message = "The built-in policy index must be a positive integer."
  }
}

variable "rules" {
  description = "Allowed initiation; replies swap endpoints and match established/related traffic only."
  type = map(object({
    description = string
    protocol    = optional(string, "all")
    ip_version  = optional(string, "BOTH")
    reply       = optional(bool, true)
    track_state = optional(bool, true)
    states      = optional(list(string), ["NEW", "ESTABLISHED", "RELATED"])
    source = object({
      zone       = string
      clients    = optional(set(string), [])
      ips        = optional(set(string), [])
      invert_ips = optional(bool, false)
      ports      = optional(string)
    })
    destination = object({
      zone       = string
      clients    = optional(set(string), [])
      ips        = optional(set(string), [])
      invert_ips = optional(bool, false)
      ports      = optional(string)
    })
  }))
  nullable = false

  validation {
    condition = alltrue([
      for rule in values(var.rules) :
      contains(concat(keys(var.zone_network_ids), keys(var.builtin_zone_ids)), rule.source.zone) &&
      contains(concat(keys(var.zone_network_ids), keys(var.builtin_zone_ids)), rule.destination.zone) &&
      rule.source.zone != rule.destination.zone &&
      contains(["all", "tcp", "udp", "tcp_udp", "icmp", "icmpv6"], rule.protocol) &&
      contains(["BOTH", "IPV4", "IPV6"], rule.ip_version) &&
      (rule.protocol != "icmpv6" || rule.ip_version == "IPV6") &&
      length(rule.states) > 0 &&
      alltrue([for state in rule.states : contains(["NEW", "ESTABLISHED", "RELATED"], state)])
    ])
    error_message = "Rules must use known, different zones and supported protocols/IP versions."
  }

  validation {
    condition = alltrue(flatten([
      for rule in values(var.rules) : [
        for endpoint in [rule.source, rule.destination] :
        !(length(endpoint.clients) > 0 && length(endpoint.ips) > 0) &&
        (!endpoint.invert_ips || length(endpoint.ips) > 0) &&
        (endpoint.ports == null || contains(["tcp", "udp", "tcp_udp"], rule.protocol)) &&
        alltrue([for mac in endpoint.clients : can(regex("^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac))]) &&
        alltrue([for ip in endpoint.ips : can(cidrhost(
          strcontains(ip, "/") ? ip : "${ip}/${strcontains(ip, ":") ? 128 : 32}", 0
        )) && (rule.ip_version == "BOTH" || (strcontains(ip, ":") == (rule.ip_version == "IPV6")))])
      ]
    ]))
    error_message = "Endpoints must use valid MACs or IPs, with IP inversion only for IP targets and ports only for TCP/UDP."
  }
}
