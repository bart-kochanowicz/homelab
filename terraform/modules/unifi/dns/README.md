# Private DNS

`records` maps stable logical keys to exact `name` and private IPv4 `address`
values. The module creates enabled A overrides with a five-minute TTL in `site`.
Names are lowercase without a trailing dot; duplicate canonical names and
wildcards are rejected. These are individual records, not an authoritative zone.

`srv_records` maps service names to a `target_record` key in `records` and a
`port`. Optional `priority` and `weight` default to zero. Targets stay private;
SRV records let supported clients discover non-default service ports.
