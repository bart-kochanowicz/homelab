variable "site" {
  description = "UniFi Network site serving the local DNS overrides."
  type        = string
  nullable    = false
}

variable "records" {
  description = "Exact private IPv4 A records keyed by stable logical names."
  type = map(object({
    name    = string
    address = string
  }))
  nullable = false

  validation {
    condition     = alltrue([for key in keys(var.records) : can(regex("^[a-z][a-z0-9_-]*$", key))])
    error_message = "Use stable logical record keys rather than DNS names or addresses."
  }

  validation {
    condition = alltrue([for record in values(var.records) :
      try(length(trimsuffix(record.name, ".")) <= 253 &&
      can(regex("^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])?$", lower(trimsuffix(record.name, ".")))), false)
    ])
    error_message = "Records must use exact, valid DNS names without wildcards or zone delegation."
  }

  validation {
    condition = try(
      length(distinct([for record in values(var.records) : lower(trimsuffix(record.name, "."))])) ==
      length(var.records), false
    )
    error_message = "Each canonical DNS name must have exactly one owner in the record map."
  }

  validation {
    condition = alltrue([for record in values(var.records) :
      can(cidrnetmask("${record.address}/32")) &&
      can(regex("^(10\\.|192\\.168\\.|172\\.(1[6-9]|2[0-9]|3[0-1])\\.)", record.address))
    ])
    error_message = "Record addresses must be valid private IPv4 addresses from RFC 1918."
  }
}
