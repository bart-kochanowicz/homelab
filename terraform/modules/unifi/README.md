# UniFi Module

LAN networks use stable map keys, generated names with `name_prefix`, optional
explicit names and DHCP pools. `subnet` contains the gateway CIDR, such as
`10.0.40.1/24`. VLANs and subnets are unique; DHCP pools exclude the gateway.
Networks have `prevent_destroy`. Provider configuration belongs to the caller.

[Provider schema](https://registry.terraform.io/providers/ubiquiti-community/unifi/0.57.0/docs/resources/network)
