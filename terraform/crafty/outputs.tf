output "crafty_url" {
  description = "Private Crafty Controller endpoint."
  value       = var.crafty_url
}

output "atm10_8_3_server_id" {
  description = "Terraform-managed active ATM10 server ID."
  value       = crafty_minecraft_server.atm10_8_3.id
}
