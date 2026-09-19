#!/bin/bash

# Restore untagged management access to the LEOX ONT after a UCG-Fiber reboot.
# Install on the UCG-Fiber as /data/on_boot.d/20-leox-management.sh.

set -u

IFACE="eth6"
LEOX_IP="192.168.100.1"
UCG_IP="192.168.100.2"

# Wait for the physical WAN interface to become available.
for ((attempt = 1; attempt <= 30; attempt++)); do
    if ip link show "$IFACE" >/dev/null 2>&1; then
        break
    fi

    sleep 1
done

if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "Interface $IFACE not found"
    exit 1
fi

# Add the management IP only if it does not already exist.
if ! ip -4 addr show dev "$IFACE" | grep -q "${UCG_IP}/24"; then
    ip addr add "${UCG_IP}/24" dev "$IFACE"
fi

# Add the SNAT rule only if it does not already exist.
if ! iptables -t nat -C POSTROUTING \
    -o "$IFACE" \
    -d "${LEOX_IP}/32" \
    -j SNAT \
    --to-source "$UCG_IP" 2>/dev/null; then

    iptables -t nat -A POSTROUTING \
        -o "$IFACE" \
        -d "${LEOX_IP}/32" \
        -j SNAT \
        --to-source "$UCG_IP"
fi
