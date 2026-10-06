module "unifi" {
  source = "../modules/unifi"

  site        = var.controller.site
  name_prefix = var.name_prefix
  networks    = var.networks
}
