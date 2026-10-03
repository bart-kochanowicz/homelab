# Public Minecraft DNS points directly to the cluster NodePort.
resource "cloudflare_dns_record" "mc_a" {
  zone_id = var.cloudflare_zone_id
  name    = "mc"
  content = var.cluster_public_ip
  type    = "A"
  proxied = false
  comment = "Managed by Terraform - Minecraft Server"
  ttl     = 1 # Automatic
}
