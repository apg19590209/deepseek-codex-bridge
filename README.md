# DeepSeek bridge for Codex (experimental)

A small, standard-library Python adapter from a subset of the Responses streaming protocol to DeepSeek Chat Completions. Independent community project; not affiliated with OpenAI or DeepSeek.

## Status

This is a local experimental adapter, not a complete Responses implementation. It has supported real multi-step Codex sessions, but occasional mid-task stops still occur. Sending `continue` has resumed such tasks; the cause remains unresolved. A normal upstream `stop` is returned as a completed response, even if the text merely announces intended work. The bridge does not automatically retry or force continuation.

## Run locally

Requires Python 3.11 or later, a DeepSeek API key, and a Codex client that accepts a custom Responses provider. No pip dependencies.

1. Download this directory into its own folder.
2. Run `python3 -m unittest discover -v` (on Windows use `python`).
3. Start `python3 -u bridge.py` in one terminal. It listens only on `127.0.0.1:8317`.
4. Set `DEEPSEEK_API_KEY` in the environment of the terminal that launches Codex, using your usual secret-management method. Do not paste a real key into a committed file or shell command history.
5. Merge `examples/config.toml` into your personal Codex configuration. Preserve your existing approval and sandbox choices; this project does not require disabling them.
6. Start a fresh Codex session and ask it to run `pwd`, then `uname -s` in a separate call (POSIX hosts), reporting both outputs without editing files. On Windows substitute `Get-Location` and `[System.Environment]::OSVersion`.

The client authorization header takes precedence over the bridge process's `DEEPSEEK_API_KEY` environment fallback. Prompts, instructions, advertised tools, and tool results are sent to DeepSeek. Usage can incur DeepSeek API charges. This does not use a ChatGPT subscription as DeepSeek credit.

Configuration reference: https://learn.chatgpt.com/docs/config-file/config-advanced

## Supported and limited behavior

- Text messages and function calls/results; developer messages map to system messages.
- Namespace function tools are flattened with request-local aliases, then restored on output.
- Commentary history receives an explicit text label; this is an approximation of Responses phases.
- Missing/orphan tool results and unsupported tool types are rejected rather than fabricated or silently discarded.
- Stream termination and arguments are checked before executable calls are returned. Truncated streams fail; length/content-filter termination is incomplete.
- Thinking is explicitly disabled. Opaque reasoning history is omitted; enabling thinking requires additional protocol work.
- No image/audio input, custom/freeform tools, built-in web tools, WebSockets, remote response storage, resume-by-response-ID, or model catalog endpoint.
- Only the implemented request fields are translated. Other options can be ignored; JSON-schema strictness is not enforced by the bridge.
- Function-call argument events and text events are buffered until upstream completion. Mixed text/tool ordering has regression coverage but has not been validated against every client.
- The HTTP layer is minimal: a 4 MiB body cap and basic JSON/auth checks exist, but there is no concurrency limit, retry policy, separate local access-token verification, or complete malformed-request handling. GET returns HTTP 501, not a health response.
- Schema and client-version changes can break compatibility. Record `codex --version`, Python version, and OS in reports; no version-wide compatibility guarantee is made.

## Tests and evidence

The 20 original offline tests cover history, namespace translation, and stream handling. Seven package regressions cover stream completion, instruction ordering, malformed HTTP input, missing authorization, and upstream failure. HTTP tests use a local server and mocked upstream responses, never real credentials or API calls. See `VALIDATION.md` for the current package checks.

Operator-reported FreeBSD testing of the predecessor included separate shell calls, a sustained multi-step session, and automatic child restart under `daemon`. Those observations are not a cross-platform certification, a reboot test, or proof that early stops are fixed.

## Service example

See `examples/freebsd/README.md`. Manual foreground operation is the simplest starting point. A service must still bind only to loopback; do not expose this HTTP server to a network. Root is not required for the bridge itself.

## Reporting problems

Include versions, a minimal synthetic request, and redacted event metadata. Do not publish credentials, real prompts, tool output, private repository paths, or configuration backups. Never publish the original development directory wholesale.

## Licence

MIT, selected by the owner. See `LICENSE`. The original adapter was AI-generated for the owner; see `PROVENANCE.md` for the disclosure and limits.
