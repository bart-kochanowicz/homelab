locals {
  cluster_connections = {
    worker-control-plane = {
      source      = "worker-01"
      destination = "control-plane-01"
      ports       = "4240,6443,50001"
      description = "Cilium health, Kubernetes API and Talos certificate issuance."
    }
    control-plane-worker = {
      source      = "control-plane-01"
      destination = "worker-01"
      ports       = "4240,10250,50000"
      description = "Cilium health, kubelet and Talos API."
    }
  }

  cluster_firewall_rules = merge(
    {
      for key, connection in local.cluster_connections : "cluster-${key}-tcp" => {
        description = connection.description
        protocol    = "tcp"
        ip_version  = "IPV4"
        source      = { zone = local.server_zones[connection.source], clients = [local.server_macs[connection.source]] }
        destination = { zone = local.server_zones[connection.destination], clients = [local.server_macs[connection.destination]], ports = connection.ports }
      }
      if local.server_zones[connection.source] != local.server_zones[connection.destination]
    },
    {
      for key, connection in local.cluster_connections : "cluster-${key}-vxlan" => {
        description = "Cilium inter-node VXLAN transport."
        protocol    = "udp"
        ip_version  = "IPV4"
        source      = { zone = local.server_zones[connection.source], clients = [local.server_macs[connection.source]] }
        destination = { zone = local.server_zones[connection.destination], clients = [local.server_macs[connection.destination]], ports = "8472" }
      }
      if local.server_zones[connection.source] != local.server_zones[connection.destination]
    },
    {
      for key, connection in local.cluster_connections : "cluster-${key}-icmp" => {
        description = "Cilium inter-node ICMP health checks and path errors."
        protocol    = "icmp"
        ip_version  = "IPV4"
        source      = { zone = local.server_zones[connection.source], clients = [local.server_macs[connection.source]] }
        destination = { zone = local.server_zones[connection.destination], clients = [local.server_macs[connection.destination]] }
      }
      if local.server_zones[connection.source] != local.server_zones[connection.destination]
    }
  )
}
