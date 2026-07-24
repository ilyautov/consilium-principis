**English** · [Русский](PRIVACY_POLICY.ru.md)

# Privacy Policy

Last updated: 2026-07-23

Consilium Principis is local-first software. The project does not operate a hosted account,
analytics, or telemetry service. Your MCP host, model provider, operating system, and any source
website have their own policies; this document describes the data flows created by this repository.

## Local data

The following data classes can be stored on the machine where you run the project. They are ignored
by Git by default and should be treated as personal data or source material:

- advisor profiles, source files, built corpora, embeddings, and calibration artefacts;
- a Principis profile and corpus, which may describe the person asking for advice;
- session transcripts, rendered council output, and audit logs created while using the board;
- decision maps, decision cards, forecasts, outcomes, and calibrated-consult records;
- federation runtime state, including its local SQLite database and replica metadata;
- source downloads and raw reference-library material used to build an advisor; and
- local configuration, including MCP configuration and environment variables that may contain
  credentials.

Do not commit this data, share it in public issues, or give it to a contributor unless you have a
lawful reason and permission to do so. Deleting the local project data is your responsibility; the
project has no central copy to delete for you.

## External data flows

Most SIMPLE-tier operations use only local Python code. The following actions can communicate
outside your machine when you choose to enable or invoke them:

- Source collection downloads the URL you provide (for example, a public-domain source). That site
  receives the normal request metadata of your network connection.
- FULL-tier semantic search sends prompts to a locally running Ollama service, normally on your own
  machine. Ollama's storage and model behaviour are governed by your Ollama installation.
- Optional OpenRouter-backed features send the request content and any supplied context needed for
  that call to OpenRouter. Enable it only with a key you control and only for data you are willing to
  send to that provider.

The project does not claim that a third-party service, host, or provider is private. Review each
provider's settings and privacy terms before sending sensitive material.

## MCP host boundary

An MCP server launched by a host runs as your user and can read or write the local data needed for
its tools. The host can request those tools and receives their results; a cloud-backed host may also
send your prompts and tool results to its model provider. Install the server only in hosts you trust,
review generated configuration with `python3 scripts/board.py mcp-config --json`, and use least
privilege where your host supports it.

## Security and questions

Report a suspected vulnerability or data exposure privately through [SECURITY.en.md](SECURITY.en.md).
For installation and ordinary usage help, see [SUPPORT.md](SUPPORT.md).
