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

variable "devices" {
  description = "Adopted devices keyed by logical identifier, managing only the declared ports."
  type = map(object({
    mac = string
    ports = map(object({
      index   = number
      profile = string
      name    = string
    }))
  }))
  default  = {}
  nullable = false

  validation {
    condition = alltrue([
      for key, device in var.devices :
      can(regex("^[a-z][a-z0-9_-]*$", key)) &&
      can(regex("^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$", device.mac)) &&
      length(device.ports) > 0 &&
      alltrue([
        for port_key, port in device.ports :
        can(regex("^[a-z][a-z0-9_-]*$", port_key)) && length(trimspace(port.name)) > 0
      ])
    ])
    error_message = "Devices and ports need non-empty logical keys, colon-separated MAC addresses, explicit port names and at least one port per device."
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
