# Security boundaries

This is a **personal, single-owner research harness**, not a public multi-tenant service.
The whole process shares one loaded model, one API configuration, and one evidence database.
Do not give the shared-link credentials to untrusted users. They would be able to change the
backend, execute explicitly allowed model code, and read/delete the owner's registered memory.

## Defaults

- Bind to 127.0.0.1. LAN bindings and Gradio share links require a password.
- Generate a random password when public binding is requested without one; never commit outputs.
- Do not persist API keys in configuration files, browser history, or chat export intentionally.
  Settings are transmitted to the server, so secure the connection and host.
- Refuse non-loopback HTTP API targets unless explicitly enabled. Disable automatic redirects
  and process-proxy inheritance so credentials are not silently sent to another URL.
- Never echo API error response bodies; they can contain prompts or credentials.
- Disable Gradio monitoring and analytics. Use system fonts, no third-party font requests.
- Block serving the evidence data directory through Gradio's file endpoint.
- Retain HTML sanitization for model outputs. Do not execute tools, code blocks, or document commands.
- Require explicit permission and a 40-character commit SHA for remote model Python code.

## What this does NOT guarantee

A model commit SHA does not sandbox code. Custom code can access files, network, credentials and
other resources available to the process. Inspect all dependencies and run untrusted models in
a separate sandbox without secrets. Hugging Face and package downloads are third-party supply-chain inputs.
The convenience launchers download and execute the official uv installer if uv is missing.
Organizations can instead preinstall approved Python/uv versions and dependencies.

Retrieved documents can contain prompt injection, falsehoods, or outdated information.
The system prompt treats them as untrusted evidence, but that is not a proof of resistance.
Citations are not automatically fact-checked. Keep human review for consequential decisions.

API mode sends the question, selected conversation history and selected document excerpts to
the configured endpoint. Do not use an external endpoint for sensitive data without approval.

The SQLite database and browser chat history are not encrypted at rest by this application.
Use OS disk encryption and private directory permissions. Browser history deletion does not
remove server memory. Memory deletion does not guarantee forensic erasure from SQLite pages,
WAL files or backups. Temporary exports are managed by Gradio's cache lifecycle, not secure deletion.

Gradio sharing depends on a third-party tunnel. Treat it as temporary, keep credentials private,
clear notebook outputs before sharing, and close the app when finished. A cancellation requests
local stopping/connection closure; remote servers may continue computing after client disconnect.

For internet-facing or multi-user deployment add proper tenant isolation, authorization per
object, rate limiting, audit policy, network policy, a reverse proxy, key management, backup and
erasure policy, supply-chain review, and a security test suite. This preview does not implement them.
