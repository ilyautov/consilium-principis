**English** · [Русский](SECURITY.md)

# Security Policy

## Reporting a vulnerability

**Do not open a public issue for vulnerabilities.** Report privately through
[GitHub Security Advisories](https://github.com/ilyautov/consilium-principis/security/advisories/new)
(the **Security → Report a vulnerability** tab).

Describe what you found, how to reproduce it, and the impact. A reasonable response time is a few
days. Please allow time for a fix before public disclosure.

## What is especially in scope

The project claims a **fail-closed fidelity contour** as its core value, so bypassing it is a
first-class vulnerability. Of particular interest:

- **Breaking the fidelity gate:** any way to make the system emit a 🔵 marker (verbatim quote) on
  text that is not in the verified corpus, or to pass a paraphrase/fabrication off as a quote.
- **Bypassing abstention:** making an advisor "invent" an off-corpus answer instead of honestly
  abstaining.
- **Defeating the moat by camouflage:** a topically-close-but-non-answering candidate that slips
  past the two-phase judge gate as 🔵.
- **Personal-data leakage:** any path by which the personal board (`advisors/`), sessions
  (`council/`), local registries, or `.env` contents could reach Git, logs, or a network request.
- **SSRF / path traversal** during corpus building, installation, or path handling.

A reproducible demonstration is doubly valued: the project runs a "a falsified experiment is a
result" culture, and a working exploit against the contour is accepted as a contribution, not an
offense.

## Boundaries

- **The core contour works offline**, without keys, network, or an external engine. If an exploit
  requires a third-party service (for example, your own OpenRouter key for tier-FULL), please say so.
- **Secrets stay with the user.** The project does not store or request keys; `.env` is in
  `.gitignore`. If you find a committed secret, that is a bug — report it privately, and we will
  rotate it and scrub the history.
- **Each user builds their own corpus.** Copyrighted material is not part of the distribution; the
  legality of anyone else's corpus is outside the perimeter of this policy.

## Content rights and notice-and-takedown

Consilium is a **verification engine, not a content distributor** (the Sony/Betamax dual-use
doctrine; under Russian law the reference point is the information intermediary, Civil Code
art. 1253.1). The key point: **the engine does not initiate or determine the content of the
corpus.** The user decides which texts to load and is responsible for holding the rights to them.
We do not host anyone's corpus on a server and do not modify material beyond technical processing
(apparatus stripping, signing, search).

The distribution includes **public-domain material only** — that is, figures of long-deceased
authors where both copyright (life + 70) and the circle of image-consent holders are exhausted
(Russian Civil Code art. 152.1, RF Supreme Court Plenum No. 25 §49). Copyrighted corpora are built
by each user from their own lawful copies and kept on their own machine (personal use, art. 1273).

**If you are a rights holder** and believe that material in our distribution (the seeded PD catalog)
infringes your rights, open a public issue with the subject prefix `takedown:` in the
[repository](https://github.com/ilyautov/consilium-principis/issues/new), stating: the material
(figure id / URL), the basis of your rights, and a contact. A reasonable response time is a few
days; a confirmed claim is satisfied by removal from the distribution (notice-and-takedown). This is
the channel for **content rights**; contour vulnerabilities go through the private Security
Advisories above.

## Supported versions

The project is in early access (`0.x`). Fixes land on `master`; there is no separate support branch
for older versions yet.
