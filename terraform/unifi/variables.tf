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

variable "infrastructure_macs" {
  description = "Private MAC inventory keyed by declared infrastructure name."
  type        = map(string)
  sensitive   = true
  nullable    = false

  validation {
    condition = (
      toset(keys(var.infrastructure_macs)) == toset(["flex-5", "voyager-01", "houston-01", "control-plane-01", "worker-01"]) &&
      alltrue([for mac in values(var.infrastructure_macs) : can(regex("^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac))]) &&
      length(distinct(values(var.infrastructure_macs))) == length(var.infrastructure_macs)
    )
    error_message = "Provide distinct lowercase MAC addresses for flex-5, voyager-01, houston-01, control-plane-01 and worker-01."
  }
}

variable "wifi_passphrases" {
  description = "Write-only Wi-Fi passphrases keyed by managed WLAN name."
  type        = map(string)
  sensitive   = true
  ephemeral   = true
  nullable    = false
}

variable "wifi_ppsks" {
  description = "Sensitive PPSK passwords keyed by WLAN/role; stored in Terraform plans and state."
  type        = map(string)
  sensitive   = true
  nullable    = false
}

variable "vpn_public_ip" {
  description = "Private input for the fixed WAN IPv4 address used by WireGuard."
  type        = string
  sensitive   = true
  nullable    = false
}

variable "vpn_peer_public_keys" {
  description = "WireGuard public keys keyed by declared peer name."
  type        = map(string)
  sensitive   = true
  nullable    = false
}
