terraform {
  required_version = ">= 1.16.4"

  required_providers {
    unifi = {
      source  = "ubiquiti-community/unifi"
      version = "0.57.0"
    }
  }
}
