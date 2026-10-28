output "crafty_url" {
  description = "Private Crafty Controller endpoint."
  value       = var.crafty_url
}

output "atm10_server_id" {
  description = "Terraform-managed ATM10 4.14 server ID."
  value       = crafty_minecraft_server.atm10.id
}

output "atm10_8_3_server_id" {
  description = "Terraform-managed ATM10 8.3 server ID."
  value       = crafty_minecraft_server.atm10_8_3.id
}
