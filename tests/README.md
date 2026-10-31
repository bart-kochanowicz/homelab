# Tests

Tests use Python's `unittest` and native tools such as Helm, kubeconform, restic
and Docker. They check rendered configuration and exercise isolated application
startup, backup and restore behavior. No production credentials are required.

## Setup and checks

Install the validation tools listed in the [root README](../README.md#local-checks).
uv selects Python from [`.python-version`](../.python-version) and installs the
dependencies pinned by [`uv.lock`](../uv.lock). Run commands from the repository root:

```bash
uv sync --locked
```

| Command | Purpose |
| --- | --- |
| `make validate` | Full repository validation, including all tests |
| `make validate-workflows` | Python tests with freshly rendered manifests and schemas |
| `make validate-python` | Pyright types, Ruff lint and format checks |
| `make format-python` | Fix imports and formatting |
| `make validate-monitoring` | Native Prometheus rule validation and test fixtures |

Start Docker before running integration tests. Individual Python modules need
the rendered manifests and schemas prepared by `make validate-workflows` or
`make validate`. After preparation, run a focused module:

```bash
uv run --locked python -m unittest tests.networking.test_n8n -v
```

Tests are grouped under `networking/`, `backups/`, `logging/` and `monitoring/`;
shared fixtures live in each package's `support.py`. Terraform's native tests
live under `terraform/unifi/tests/` and run through `make validate-terraform-tests`.

## VS Code

Install the workspace's recommended Python, Pylance and Ruff extensions, then
select `.venv` with **Python: Select Interpreter**. Python files format on save;
the Testing panel uses unittest. Prepare rendered fixtures before using that panel.

Pyright and Pylance share the type-checking configuration in
[`pyproject.toml`](../pyproject.toml), including errors for unknown member types.
