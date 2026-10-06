module "unifi" {
  source = "../modules/unifi"

  providers = {
    unifi = unifi
  }

  site        = var.controller.site
  name_prefix = var.name_prefix
  networks    = var.networks
}
