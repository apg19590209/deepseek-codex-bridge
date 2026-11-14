# Local package validation

- Python 3.11 on Windows: 27 offline tests passed (20 original unit tests and seven package regressions, including local HTTP/mock-upstream tests).
- All packaged Python files parsed successfully; example configuration parsed as TOML.
- Three helper modules and the original three test modules match the repaired local sources after newline normalization.
- Package scan found no known private host/user identifiers, key-shaped tokens, or PEM private keys. This is a targeted scan, not a guarantee that every possible secret can be detected.
- The archive is built from this clean directory only; caches, original bridge, logs, configuration backups, repository history, and appliance evidence are excluded.
- GitHub Actions workflow is retained in the local source archive but omitted from this initial public commit because the publishing token lacks workflow scope. No actual DeepSeek request, FreeBSD service installation, production contact, or reboot was performed during packaging.
- Source-level limitations are listed in README.md and SECURITY.md. HTTP errors and request limits received focused fixes; protocol coverage and resource isolation still need further work before broader deployment.

A SHA256SUMS file covers the package files except itself. The ZIP has a separate SHA-256 sidecar. Clean extraction and tests are checked before delivery.
