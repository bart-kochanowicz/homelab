# UniFi Infrastructure

This directory contains source-controlled, credential-free operational material
for the UniFi Cloud Gateway Fiber (UCG-Fiber). It does not configure the gateway
automatically; install the documented runtime script on the gateway after
reviewing it.

## Contents

- [WAN / Netia GPON](docs/wan-netia.md): topology, installation, smoke test,
  and recovery procedure.
- [LEOX management restoration script](scripts/leox-management.sh): restores
  the UCG-Fiber's untagged management path after a reboot.
