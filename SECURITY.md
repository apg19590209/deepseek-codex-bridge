# Security and privacy

Bind only to loopback. The bridge is intended for a trusted local account, not shared-host or network service use. Any local client can use the bridge process's fallback API key when configured. Incoming Authorization is forwarded to DeepSeek; there is no separate local access control.

Requests without a client bearer token or a process-level fallback key are rejected. This check does not authenticate the identity of a local client: with a process-level fallback key, any local process able to reach the loopback port can use it.

No credentials are included in this package. Supply your own key through the environment and protect service logs and secret files. Metadata logs omit prompt bodies, but upstream HTTP error bodies are returned to the caller and unhandled exceptions may produce tracebacks. Review logs before sharing them.

Do not file public issues containing secrets or private request data. A private security contact has not yet been configured. Remove sensitive details before reporting an issue.
