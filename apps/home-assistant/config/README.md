# Home Assistant content

This directory has the layout of Home Assistant's `/config` and holds what Home Assistant
does, not how it runs: packages, YAML dashboards and the scripts of custom cards. The
platform (`configuration.yaml`, mounts, TLS, network policies, backups) is in the parent
directory.

- `packages/<feature>.yaml`: everything for one feature, loaded by
  `homeassistant.packages` in `../configmap.yaml`.
- `dashboards/<name>.yaml`: a YAML dashboard, registered under `lovelace.dashboards`
  in a package.
- `www/<name>/`: scripts of custom cards, served by `/local` **without authentication**.
  Put nothing but scripts here, never pictures or data.

Every file must be listed in a `configMapGenerator` in `../kustomization.yaml`; each
folder is mounted at the same path under `/config`. See
[Home Assistant content](../../../docs/security-runbook.md#home-assistant-content).
