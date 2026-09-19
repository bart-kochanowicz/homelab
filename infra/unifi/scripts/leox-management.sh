#!/bin/bash

IFACE="eth6"
VLAN_IFACE="eth6.35"

LEOX_IP="192.168.100.1"
UCG_IP="192.168.100.2"

CHECK_INTERVAL=60
PIDFILE="/run/leox-management.pid"

# Prevent multiple watchdog instances.
if [ -f "$PIDFILE" ]; then
    OLD_PID="$(cat "$PIDFILE" 2>/dev/null)"

    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        exit 0
    fi

    rm -f "$PIDFILE"
fi

(
    trap 'rm -f "$PIDFILE"' EXIT INT TERM

    while true; do
        # Only operate when the expected WAN interfaces exist.
        if ip link show "$IFACE" >/dev/null 2>&1 &&
           ip link show "$VLAN_IFACE" >/dev/null 2>&1; then

            # Remove legacy /24 configuration if it is still present.
            if ip -4 addr show dev "$IFACE" | grep -q "${UCG_IP}/24"; then
                ip addr del "${UCG_IP}/24" dev "$IFACE"

                logger -t leox-management \
                    "Removed legacy ${UCG_IP}/24 from ${IFACE}"
            fi

            # Restore the UCG management source address as a host address.
            if ! ip -4 addr show dev "$IFACE" | grep -q "${UCG_IP}/32"; then
                ip addr add "${UCG_IP}/32" dev "$IFACE"

                logger -t leox-management \
                    "Restored ${UCG_IP}/32 on ${IFACE}"
            fi

            # Explicit host route to the LEOX management interface.
            ip route replace "${LEOX_IP}/32" \
                dev "$IFACE" \
                scope link \
                src "$UCG_IP" \
                >/dev/null 2>&1

            # Restore SNAT if UniFi rebuilds the firewall.
            if ! iptables -t nat -C POSTROUTING \
                -o "$IFACE" \
                -d "${LEOX_IP}/32" \
                -j SNAT \
                --to-source "$UCG_IP" \
                >/dev/null 2>&1; then

                iptables -t nat -A POSTROUTING \
                    -o "$IFACE" \
                    -d "${LEOX_IP}/32" \
                    -j SNAT \
                    --to-source "$UCG_IP"

                logger -t leox-management \
                    "Restored SNAT for ${LEOX_IP}"
            fi
        fi

        sleep "$CHECK_INTERVAL"
    done
) &