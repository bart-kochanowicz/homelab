output "crafty_url" {
  description = "Private Crafty Controller endpoint."
  value       = var.crafty_url
}

output "atm10_server_id" {
  description = "Terraform-managed ATM10 server ID."
  value       = crafty_minecraft_server.atm10.id
}
