terraform {
  required_providers {
    crafty = {
      source  = "bart-kochanowicz/crafty"
      version = "0.1.8"
    }
  }
}

provider "crafty" {
  url   = var.crafty_url
  token = var.crafty_token
}
