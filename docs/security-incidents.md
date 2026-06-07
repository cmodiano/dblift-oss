# Security incidents log

Incidents are tracked here with their detection, remediation, and
verification steps. Entries are append-only; never edit a past entry
except to update its status.

---

## 2026-04-19 — Hardcoded credential in `scripts/setup_mysql_remote.sh`

**Severity**: Medium. Credential targets a private-network asset,
not internet-accessible. Specific host and account details are
maintained in the maintainers' internal remediation tracker, not in
this public log.

**Detection**: gitleaks 8.24.3 scan during PR-0E baseline on PR 161.
Rule: `generic-api-key`. File: `scripts/setup_mysql_remote.sh` L13.

**History**: introduced via two prior commits (allowlisted in
`.gitleaks.toml` by full SHA). Present from those commits onward in
HEAD of `develop` / `main` until the remediation below.

**What leaked**: a hardcoded `DBLIFT_MYSQL_PASSWORD` value (specific
host, account, and secret handled privately — see the maintainers'
internal tracker).

**Remediation**:

1. **Code** — `scripts/setup_mysql_remote.sh` refactored to require
   `DBLIFT_MYSQL_PASSWORD` from the environment (via `: "${VAR:?...}"`
   Bash pattern). No default, no silent fallback.
2. **Allowlist** — the two historical commits added to
   `.gitleaks.toml` `[allowlist].commits` by full SHA.
3. **History rewrite** — NOT performed. Rationale: the affected
   asset is on a private network not reachable from the internet,
   and rewriting history invalidates every existing clone and review
   reference. Cost > benefit.
4. **Credential rotation** — handled via the maintainers' internal
   tracker, not this public log.

**Verification**:

- `gitleaks detect --config .gitleaks.toml` reports no leaks.
- `grep -RE 'DBLIFT_MYSQL_PASSWORD\s*=\s*["\x27]\w' scripts/ api/ cli/ core/ db/`
  returns no hardcoded value.

**Status**: Code remediation shipped. Operational remediation tracked
privately.

---

## Template for future incidents

Copy the block above. Required sections: Severity, Detection, History,
What leaked, Remediation, Verification, Status.
