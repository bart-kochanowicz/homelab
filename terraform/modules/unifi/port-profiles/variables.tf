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
  description = "Prefix for generated port profile names."
  type        = string
  default     = "cavespace-"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*-$", var.name_prefix))
    error_message = "The prefix must use lowercase letters, digits or hyphens and end with a hyphen."
  }
}

variable "network_ids" {
  description = "Managed network IDs keyed by the logical names used in port profiles."
  type        = map(string)
  nullable    = false
}

variable "reserved_network_ids" {
  description = "Read-only LAN IDs to include when excluding networks from trunks."
  type        = set(string)
  default     = []
  nullable    = false
}

variable "port_profiles" {
  description = "Port profiles referencing managed logical network keys; an empty tag set defines an access port."
  type = map(object({
    native_network  = string
    tagged_networks = optional(set(string), [])
  }))
  default  = {}
  nullable = false

  validation {
    condition = alltrue([
      for key, profile in var.port_profiles :
      can(regex("^[a-z][a-z0-9_-]*$", key)) &&
      contains(keys(var.network_ids), profile.native_network) &&
      alltrue([for network in profile.tagged_networks : contains(keys(var.network_ids), network)]) &&
      !contains(profile.tagged_networks, profile.native_network)
    ])
    error_message = "Profiles must reference existing managed networks and cannot tag their native network."
  }
}
