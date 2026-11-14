# FreeBSD / OPNsense service example

Review paths and existing listeners before installing. Do not interrupt an active Codex task. This example runs as root when started by root; use a dedicated account and appropriate PID/log permissions when adapting for a shared host. It is not a security-hardened installer.

Copy `bridge.py`, `bridge_history.py`, `bridge_namespaces.py`, and `bridge_stream.py` to `/usr/local/libexec/deepseek-codex/`. Keep that directory and its files writable only by the service administrator. Install `deepseek_codex` as `/usr/local/etc/rc.d/deepseek_codex`, mode 0755. Verify `/usr/local/bin/python3` exists.

On OPNsense put `deepseek_codex_enable="YES"` in `/etc/rc.conf.d/deepseek_codex`. On ordinary FreeBSD use the normal rc.conf service-enable mechanism. Do not overwrite existing configuration blindly. This example expects credentials from the Codex client's Authorization header; it does not embed or load an API key.

Use `service deepseek_codex start`, `status`, `stop`, or `restart`. The supervisor PID is in `/var/run/deepseek_codex.pid`; the child PID is separate. `daemon -r -R 5` restarts a terminated child after five seconds. Stop the service through `service`, not by killing only its child. Logs are in `/var/log/deepseek_codex.log`; arrange rotation for prolonged use.

Validate an actual two-tool Codex request before retiring an old listener. A local HTTP response only proves the server is listening. Startup registration is not evidence of a successful reboot test. Keep the prior script/configuration backup for rollback; stopping this service and restoring the former configuration/launcher is a manual operation.

References:
- https://docs.opnsense.org/development/backend/autorun.html
- https://man.freebsd.org/cgi/man.cgi?query=daemon&sektion=8
