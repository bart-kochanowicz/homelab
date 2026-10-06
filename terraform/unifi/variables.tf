variable "controller" {
  description = "Local UniFi HTTPS origin and Network site name."
  type = object({
    url  = string
    site = optional(string, "default")
  })
  nullable = false

  validation {
    condition     = can(regex("^https://[a-zA-Z0-9][a-zA-Z0-9.-]*(:[0-9]+)?/?$", var.controller.url))
    error_message = "Use an HTTPS origin without credentials, API paths, queries or fragments."
  }

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9_-]*$", var.controller.site))
    error_message = "The site must be a non-empty lowercase UniFi site name."
  }
}

variable "unifi_auth" {
  description = "Dedicated local UniFi credentials or API key."
  type = object({
    username = optional(string)
    password = optional(string)
    api_key  = optional(string)
  })
  sensitive = true
  ephemeral = true
  nullable  = false

  validation {
    condition = (
      var.unifi_auth.api_key != null
      ? try(length(trimspace(var.unifi_auth.api_key)) > 0, false) && var.unifi_auth.username == null && var.unifi_auth.password == null
      : try(length(trimspace(var.unifi_auth.username)) > 0 && length(var.unifi_auth.password) > 0, false)
    )
    error_message = "Provide either a non-empty API key or a non-empty local username/password pair."
  }
}

variable "name_prefix" {
  description = "Prefix for generated UniFi object names."
  type        = string
  default     = "cavespace-"
  nullable    = false
}

variable "networks" {
  description = "LAN networks keyed by stable logical identifiers; subnet contains the gateway address."
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
    condition = alltrue([
      for network in values(var.networks) : try(
        cidrhost("${cidrhost(network.subnet, 0)}/${split("/", data.unifi_network.default.subnet)[1]}", 0) != cidrhost(data.unifi_network.default.subnet, 0) &&
        cidrhost("${cidrhost(data.unifi_network.default.subnet, 0)}/${split("/", network.subnet)[1]}", 0) != cidrhost(network.subnet, 0), false
      )
    ])
    error_message = "Managed LAN subnets must not overlap the built-in Default LAN."
  }
}
