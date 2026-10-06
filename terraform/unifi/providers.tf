terraform {
  required_providers {
    unifi = {
      source  = "ubiquiti-community/unifi"
      version = "0.57.0"
    }
  }
}

provider "unifi" {
  api_url         = var.controller.url
  site            = var.controller.site
  username        = var.unifi_auth.username
  password        = var.unifi_auth.password
  api_key         = var.unifi_auth.api_key
  allow_insecure  = false
  cloud_connector = false
}
