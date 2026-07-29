# Public release checklist

Use this checklist for every public release. It is intentionally repository-host agnostic.

## Source boundary

- [ ] Review `git status --short`, `git ls-files`, and the complete release diff.
- [ ] Confirm `.env`, local agent/editor settings, logs, reference material, customer data, and
      private design or audit notes are not tracked.
- [ ] Scan the exact history that will be published with
      `gitleaks git --config .gitleaks.toml`.
- [ ] If private development history contains material that should not be public, publish from a
      new clean lineage; deleting a file in a later commit does not remove it from history.
- [ ] Verify a fresh clone, rather than the working directory, before publishing.

## Correctness and supply chain

- [ ] Run `make check`.
- [ ] Run `docker compose config --quiet` and build both container images.
- [ ] Review dependency audit output and all automated dependency updates.
- [ ] Confirm CI passes on every supported Python and Node.js version.
- [ ] Confirm Mock mode starts with no `.env` and makes no outbound runtime request.

## Legal and privacy

- [ ] Review `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `ASSETS.md`, and
      `KNOWLEDGE_SOURCES.md`.
- [ ] Recompute distributed asset sizes and SHA-256 values.
- [ ] Confirm screenshots and demo videos contain no credentials, local paths, account names,
      private tabs, notifications, or customer information.
- [ ] Confirm every third-party asset carries its required attribution in both the repository and
      any standalone release artifact.

## Repository settings

- [ ] Set the repository description, topics, homepage, default branch, and release version.
- [ ] Enable private vulnerability reporting and Dependabot security updates.
- [ ] Protect the default branch and require CI for changes.
- [ ] Confirm Issue and Pull Request templates point security reports to `SECURITY.md`.

## Release

- [ ] Update `CHANGELOG.md` and add release comparison links after the public repository URL is
      known.
- [ ] Tag the reviewed commit and attach only artifacts built from that commit.
- [ ] Download the published source archive and repeat the secret and asset spot checks.
