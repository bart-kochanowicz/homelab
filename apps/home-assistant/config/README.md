# Home Assistant content

This directory has the layout of Home Assistant's `/config` and holds what Home Assistant
does, not how it runs: packages and the scripts of custom cards (and YAML dashboards, if one is added). The
platform (`configuration.yaml`, mounts, TLS, network policies, backups) is in the parent
directory.

- `packages/<feature>.yaml`: everything for one feature, loaded by
  `homeassistant.packages` in `../configmap.yaml`.
- `dashboards/<name>.yaml`: a YAML dashboard, registered under `lovelace.dashboards`
  in a package. There is none now: add the folder, a `configMapGenerator` entry and a
  mount (the removed front-door dashboard had all three).
- `www/<name>/`: scripts of custom cards, served by `/local` **without authentication**.
  Put nothing but scripts here, never pictures or data.

Every file must be listed in a `configMapGenerator` in `../kustomization.yaml`; each
folder is mounted at the same path under `/config`. See
[Home Assistant content](../../../docs/security-runbook.md#home-assistant-content).

## When this outgrows the repository

Each limit below is a sign to act:

- **Moving it out.** Many packages, dashboards or cards, or changes here drowning out
  platform changes: make this directory the root of its own repository and have an init
  container (or a `git-sync` sidecar) clone it at a pinned commit into `/config`. The
  generators also stop working at 1 MiB per ConfigMap. The steps are in the runbook
  section linked above.
- **Splitting a card.** Each card is one script with its CSS inline. A relative `import`
  does not carry the `?v=` that busts `/local`'s 31-day cache, and `.css` imports need a
  recent Safari, so split only with a build step (for example esbuild) that bundles
  `src/` into one script whose name or `?v=` changes with its content.
