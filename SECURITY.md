# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x (latest release) | Yes |
| Older builds | No; please update to the latest release |

## Reporting a vulnerability

Please report security problems **privately** through GitHub's private vulnerability reporting:

**[Report a vulnerability](https://github.com/baki2222/printscale-studio/security/advisories/new)** (Security tab › Report a vulnerability)

Please include:
- the PrintScale Studio version and Windows version;
- what an attacker could do, and how to reproduce it;
- a minimal sample file if one is needed. Do not include personal images.

Do not open a public issue for security problems. You should get a first response within 7 days. Once a fix is
released, the advisory is published with credit to you, unless you prefer to stay anonymous.

## Scope

- **In scope:**
  - malformed image files that cause crashes or code execution;
  - files written outside the chosen destination;
  - unsafe handling of metadata;
  - problems in the installer or the model download script (`scripts/fetch_models.py`).
- **The app is offline:** it makes no network connections, and the bundled models are verified against pinned SHA-256 hashes before loading.
- **Out of scope:**
  - the unsigned-installer SmartScreen warning;
  - vulnerabilities in third-party components that are already fixed upstream. Please still tell us, so the dependency can be updated.
