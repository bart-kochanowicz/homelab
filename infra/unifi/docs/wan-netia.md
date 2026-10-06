# Netia GPON WAN

Netia GPON connects through the LEOX LXT-010S-H ONT to the UCG-Fiber,
which terminates PPPoE. Keep PPPoE credentials, GPON identity values and the
LEOX parameter backup outside Git.

| Connection | Configuration |
| --- | --- |
| SFP link | `eth6`, forced to 1 Gbps / 1GBase-X |
| Internet | VLAN 35 on `eth6.35`, PPPoE on UCG-Fiber |
| LEOX management | Untagged `eth6`, LEOX at `192.168.100.1` |
| UCG management source | `192.168.100.2/32` on `eth6` |
| Management route | `192.168.100.1/32 dev eth6 scope link src 192.168.100.2` |
| Management NAT | SNAT to `192.168.100.2` for traffic to LEOX |

## Persistent management access

[`leox-management.sh`](../scripts/leox-management.sh) runs from the UCG-Fiber's
`unifi-common` / `on_boot.d` hook at `/data/on_boot.d/20-leox-management.sh`.
Install and start it on the gateway:

```bash
install -m 0755 leox-management.sh /data/on_boot.d/20-leox-management.sh
/data/on_boot.d/20-leox-management.sh
```

Every 60 seconds, the watchdog checks for `eth6` and `eth6.35`, restores the
host address and route, and restores SNAT after UniFi rebuilds the firewall.

## Verification and recovery

On UCG-Fiber, check the management address, route and SNAT rule:

```bash
ip -4 addr show dev eth6
ip route get 192.168.100.1
iptables -t nat -C POSTROUTING -o eth6 -d 192.168.100.1/32 \
  -j SNAT --to-source 192.168.100.2
ping -c 4 192.168.100.1
ping -c 4 1.1.1.1
```

From a LAN device, open [LEOX management](http://192.168.100.1).

For WAN recovery, verify the 1 Gbps SFP link, GPON registration, VLAN 35,
PPPoE session and public WAN IP. On LEOX, `diag gpon get onu-state` must
report `Operation State(O5)`. Restore the private LEOX parameter backup if
GPON registration fails. For management recovery, verify the `/32` address,
host route and SNAT rule, then restart the watchdog if needed.
