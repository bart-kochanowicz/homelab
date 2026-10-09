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
  description = "Prefix for generated SSID names."
  type        = string
  default     = "cavespace-"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*-$", var.name_prefix))
    error_message = "The prefix must use lowercase letters, digits or hyphens and end with a hyphen."
  }
}

variable "network_ids" {
  description = "Managed network IDs keyed by the logical names used in WLANs."
  type        = map(string)
  nullable    = false
}

variable "ap_group_id" {
  description = "Existing default AP group ID used to broadcast WLANs on all access points."
  type        = string
  nullable    = false
}

variable "user_group_id" {
  description = "Existing client QoS group ID applied to WLAN clients."
  type        = string
  nullable    = false
}

variable "wlans" {
  description = "WPA3-only WLANs referencing managed logical network keys and 2.4/5 GHz bands."
  type = map(object({
    network = string
    bands   = set(string)
  }))
  nullable = false

  validation {
    condition = alltrue([
      for key, wlan in var.wlans :
      can(regex("^[a-z][a-z0-9_-]*$", key)) &&
      length("${var.name_prefix}${key}") <= 32 &&
      contains(keys(var.network_ids), wlan.network)
    ])
    error_message = "WLAN keys must use lowercase names, produce SSIDs of at most 32 characters and reference existing managed networks."
  }

  validation {
    condition = alltrue([
      for wlan in values(var.wlans) :
      length(wlan.bands) > 0 && alltrue([for band in wlan.bands : contains(["2g", "5g"], band)])
    ])
    error_message = "Each WLAN must select at least one band from 2g and 5g."
  }
}

variable "passphrases" {
  description = "Write-only WPA3 passphrases keyed by WLAN logical identifier."
  type        = map(string)
  sensitive   = true
  ephemeral   = true
  nullable    = false

  validation {
    condition     = toset(keys(var.passphrases)) == toset(keys(var.wlans))
    error_message = "Provide exactly one passphrase for every configured WLAN."
  }

  validation {
    condition     = alltrue([for passphrase in values(var.passphrases) : try(length(passphrase) >= 8 && length(passphrase) <= 63, false)])
    error_message = "WLAN passphrases must contain between 8 and 63 characters."
  }
}

variable "ppsk_wlans" {
  description = "WPA2 PPSK WLANs with role-to-network bindings and a default role for the WLAN network."
  type = map(object({
    bands       = set(string)
    keys        = map(string)
    default_key = string
  }))
  default  = {}
  nullable = false

  validation {
    condition = alltrue([
      for key, wlan in var.ppsk_wlans :
      can(regex("^[a-z][a-z0-9_-]*$", key)) &&
      length("${var.name_prefix}${key}") <= 32 &&
      !contains(keys(var.wlans), key) &&
      length(wlan.keys) > 0 && contains(keys(wlan.keys), wlan.default_key) &&
      alltrue([for role, network in wlan.keys :
        can(regex("^[a-z][a-z0-9_-]*$", role)) && contains(keys(var.network_ids), network)
      ])
    ])
    error_message = "PPSK WLANs must have unique valid names of at most 32 characters, valid roles bound to managed networks and a default role present in their keys."
  }

  validation {
    condition = alltrue([
      for wlan in values(var.ppsk_wlans) :
      length(wlan.bands) > 0 && alltrue([for band in wlan.bands : contains(["2g", "5g"], band)])
    ])
    error_message = "PPSK WLANs require at least one band from 2g and 5g; WPA2 PPSK does not support 6 GHz."
  }
}

variable "ppsk_passphrases" {
  description = "Sensitive PPSK passwords keyed by WLAN/role; stored in Terraform plans and state."
  type        = map(string)
  default     = {}
  sensitive   = true
  nullable    = false

  validation {
    condition = length(var.ppsk_passphrases) == sum(concat([0], [for config in values(var.ppsk_wlans) : length(config.keys)])) && alltrue([
      for wlan, config in var.ppsk_wlans : alltrue([
        for role in keys(config.keys) : contains(keys(var.ppsk_passphrases), "${wlan}/${role}")
      ])
    ])
    error_message = "Provide exactly one PPSK password for each configured WLAN/role."
  }

  validation {
    condition     = alltrue([for password in values(var.ppsk_passphrases) : try(length(password) >= 8 && length(password) <= 63, false)])
    error_message = "PPSK passwords must contain between 8 and 63 characters."
  }

  validation {
    condition = alltrue([
      for wlan, config in var.ppsk_wlans :
      length(distinct([for role in keys(config.keys) : lookup(var.ppsk_passphrases, "${wlan}/${role}", null)])) == length(config.keys)
    ])
    error_message = "Passwords for different roles on the same PPSK WLAN must be distinct."
  }
}
