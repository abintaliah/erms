# Wathiq / ERMS

Wathiq provides records management with an independently deployed FastAPI API
and NiceGUI WebUI.

For local development, start with [local setup](docs/full-text-search-local-setup.md)
and the [WebUI README](frontend/webui/README.md). Run `./run-local-stack.sh` from
the repository root to start the local services.

Message capture (**Save record**) requires local veraPDF and Java. These tools
are intentionally excluded from Git and must be installed on each colleague's
machine. See [local tooling and installation](docs/local-tooling.md) and the
[message capture upgrade note](docs/upgrades/message-capture-validator.md).
The local stack reports a missing validator with the setup command while
allowing other features to start.

See [deployment documentation](docs/deployment.md) for deployment requirements
and [database instructions](database/README.md) for schema and migrations.
