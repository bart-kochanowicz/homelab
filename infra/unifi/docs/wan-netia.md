# Netia GPON WAN

## Purpose and scope

Netia provides the GPON service. The original Huawei HG8245X6-10 has been
replaced by a LEOX LXT-010S-H, which acts only as the optical network terminal
(ONT). The UniFi Cloud Gateway Fiber (UCG-Fiber) remains the router and
terminates the Internet connection.

This document deliberately excludes PPPoE credentials, GPON identity values,
hardware serial numbers, and device backups. Keep the private LEOX parameter
backup outside the repository; never add it to Git.

## WAN architecture

```text
Netia GPON
    |
    v
LEOX LXT-010S-H (ONT only; healthy GPON state: O5 / Operation State)
    |
    v
UCG-Fiber eth6 (physical WAN; SFP link forced to 1 Gbps / 1GBase-X)
    |
    +-- untagged management traffic
    |     |
    |     +-- LEOX management address: 192.168.100.1
    |     +-- UCG management address:  192.168.100.2/24
    |
    +-- VLAN 35 Internet traffic
          |
          +-- eth6.35
                |
                +-- PPPoE terminated by UCG-Fiber
                      |
                      +-- Internet
```

Management traffic stays untagged on `eth6`. Netia Internet traffic uses VLAN
35 on `eth6.35`, with PPPoE terminated on the UCG-Fiber. The SFP Ethernet link
must be forced to 1 Gbps / 1GBase-X.

The UCG uses `192.168.100.2/24` on its physical WAN interface to reach the
LEOX at `192.168.100.1`. Source NAT (SNAT) is necessary so that LAN clients
accessing the LEOX receive return traffic addressed to the UCG management IP.

## Persistent LEOX management access

The UCG-Fiber's `unifi-common` / `on_boot.d` mechanism restores the runtime
configuration after gateway reboots. The source-controlled script is
[`../scripts/leox-management.sh`](../scripts/leox-management.sh) and must be
installed on the UCG-Fiber as `/data/on_boot.d/20-leox-management.sh`.

From a trusted administrative session on the UCG-Fiber, copy the reviewed
script to that path and make it executable:

```bash
install -m 0755 leox-management.sh /data/on_boot.d/20-leox-management.sh
```

Run it once after installation, or reboot the UCG-Fiber during an approved
maintenance window:

```bash
/data/on_boot.d/20-leox-management.sh
```

The script is idempotent: it waits for `eth6`, adds `192.168.100.2/24` only
when absent, and adds the targeted `POSTROUTING` SNAT rule only when absent.
It does not contain or configure PPPoE or GPON credentials.

## Smoke test

After installing the script or rebooting the UCG-Fiber, run these checks on the
UCG-Fiber:

```bash
ip addr show dev eth6 | grep 192.168.100.2

ip route get 192.168.100.1

ping -c 4 192.168.100.1

iptables -t nat -C POSTROUTING \
  -o eth6 \
  -d 192.168.100.1/32 \
  -j SNAT \
  --to-source 192.168.100.2

ping -c 4 1.1.1.1
```

On the LEOX, check GPON registration:

```bash
diag gpon get onu-state
```

Expected result:

```text
ONU state: Operation State(O5)
```

From a LAN device, verify the management path and then open the local LEOX
interface:

```bash
ping 192.168.100.1
```

LEOX Web UI: <http://192.168.100.1>

## Disaster recovery checklist

1. Verify the physical SFP link is up at 1 Gbps / 1GBase-X.
2. Verify GPON reaches O5 / Operation State.
3. Verify VLAN 35 is present on `eth6.35`.
4. Verify the PPPoE session is established.
5. Verify the UCG-Fiber has a public WAN IP.
6. Verify `192.168.100.2/24` exists on `eth6`.
7. Verify the targeted SNAT rule exists in the `nat` table.
8. If GPON registration fails, use the private LEOX parameter backup; do not
   copy it into this repository.
