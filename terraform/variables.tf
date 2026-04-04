variable "cloudflare_api_token" {
  description = "Cloudflare API token with permissions for Tunnel, Access, and DNS"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for your domain"
  type        = string
}

variable "domain" {
  description = "Base domain name (e.g., example.com)"
  type        = string
}

variable "argocd_subdomain" {
  description = "Subdomain for ArgoCD (e.g., argocd)"
  type        = string
  default     = "argocd"
}

variable "tunnel_name" {
  description = "Name for the Cloudflare Tunnel"
  type        = string
  default     = "homelab-tunnel"
}

variable "argocd_service_url" {
  description = "Internal Kubernetes service URL for ArgoCD"
  type        = string
  default     = "https://argocd-server.argocd.svc.cluster.local"
}

variable "allowed_emails" {
  description = "List of email addresses allowed to access ArgoCD via Cloudflare Access"
  type        = list(string)
  default     = []
}

variable "crafty_controller_subdomain" {
  description = "Subdomain for Crafty Controller (e.g., crafty-controller)"
  type        = string
  default     = "crafty-controller"
}

variable "crafty_controller_service_url" {
  description = "Internal Kubernetes service URL for Crafty Controller"
  type        = string
  default     = "https://crafty-controller.crafty-controller.svc.cluster.local:8443"
}

variable "cluster_public_ip" {
  description = "Public IP address of the cluster"
  type        = string
  sensitive   = true
}

variable "grafana_service_url" {
  description = "Internal Kubernetes service URL for Grafana"
  type        = string
  default     = "http://kube-prometheus-stack-grafana.monitoring.svc.cluster.local:80"
}

variable "home_assistant_subdomain" {
  description = "Subdomain for Home Assistant"
  type        = string
  default     = "home-assistant"
}

variable "home_assistant_service_url" {
  description = "Internal Kubernetes service URL for Home Assistant"
  type        = string
  default     = "http://home-assistant.home-assistant.svc.cluster.local:8123"
}

variable "n8n_subdomain" {
  description = "Subdomain for the n8n editor"
  type        = string
  default     = "n8n"
}

variable "n8n_webhook_subdomain" {
  description = "Subdomain for public n8n webhook traffic"
  type        = string
  default     = "n8n-webhook"
}

variable "n8n_service_url" {
  description = "Internal Kubernetes service URL for n8n"
  type        = string
  default     = "http://n8n.n8n.svc.cluster.local:5678"
}
