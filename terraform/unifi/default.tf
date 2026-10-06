data "unifi_network" "default" {
  site = var.controller.site
  name = "Default"

  lifecycle {
    postcondition {
      condition     = self.purpose == "corporate" && can(cidrnetmask(self.subnet))
      error_message = "Default must be a routed corporate IPv4 LAN."
    }
  }
}
