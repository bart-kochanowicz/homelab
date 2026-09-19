#!/bin/bash

IFACE="eth6"
LEOX_IP="192.168.100.1"
UCG_IP="192.168.100.2"
CHECK_INTERVAL=30

(
    while true; do
        if ip link show "$IFACE" >/dev/null 2>&1; then

            if ! ip -4 addr show dev "$IFACE" | grep -q "${UCG_IP}/24"; then
                ip addr replace "${UCG_IP}/24" dev "$IFACE"
            fi

            ip route replace "${LEOX_IP}/32" \
                dev "$IFACE" \
                src "$UCG_IP" \
                >/dev/null 2>&1

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
            fi
        fi

        sleep "$CHECK_INTERVAL"
    done
) &