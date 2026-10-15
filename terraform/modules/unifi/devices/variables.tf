variable "site" {
  description = "UniFi Network site managed by the module."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9_-]*$", var.site))
    error_message = "The site must be a non-empty lowercase UniFi site name."
  }
}

variable "port_profile_ids" {
  description = "UniFi port profile IDs keyed by logical identifier."
  type        = map(string)
  nullable    = false
}

variable "network_ids" {
  description = "Network IDs keyed by logical name for tagged device management."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "devices" {
  description = "Adopted devices with declared ports and optional tagged management network."
  type = map(object({
    mac                = string
    management_network = optional(string)
    ports = optional(map(object({
      index    = number
      profile  = string
      name     = string
      poe_mode = optional(string)
    })), {})
  }))
  default  = {}
  nullable = false

  validation {
    condition = alltrue([
      for key, device in var.devices :
      can(regex("^[a-z][a-z0-9_-]*$", key)) &&
      can(regex("^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$", device.mac)) &&
      (length(device.ports) > 0 || device.management_network != null) &&
      alltrue([
        for port_key, port in device.ports :
        can(regex("^[a-z][a-z0-9_-]*$", port_key)) && length(trimspace(port.name)) > 0
      ])
    ])
    error_message = "Devices need logical keys, valid MACs and at least one declared port or management network; declared ports need names."
  }

  validation {
    condition = alltrue([
      for device in values(var.devices) :
      device.management_network == null ? true : contains(keys(var.network_ids), device.management_network)
    ])
    error_message = "Management networks must reference a declared network ID."
  }

  validation {
    condition = (
      length(distinct([for device in values(var.devices) : lower(device.mac)])) == length(var.devices)
    )
    error_message = "Each device MAC address must be managed only once, regardless of letter case."
  }

  validation {
    condition = alltrue([
      for device in values(var.devices) :
      alltrue([for port in values(device.ports) : port.index >= 1 && floor(port.index) == port.index]) &&
      length(distinct([for port in values(device.ports) : port.index])) == length(device.ports)
    ])
    error_message = "Port indices must be positive integers and unique within each device."
  }

  validation {
    condition = alltrue(flatten([
      for device in values(var.devices) : [
        for port in values(device.ports) : contains(keys(var.port_profile_ids), port.profile)
      ]
    ]))
    error_message = "Every declared port must reference an existing port profile."
  }
}
