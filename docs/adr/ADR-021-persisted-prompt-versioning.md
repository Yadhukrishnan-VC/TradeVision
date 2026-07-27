# ADR-021: Persisted Prompt Versioning & Rollback

**Status:** Draft
**Date:** 2026-07-27
**Deciders:** Principal AI Architect (Intelligence domain)

## Context

ADR-016 defined file-based prompt templates with content-hash versioning. Batch B requires governed version promotion: activate, rollback, and audit history without modifying template files.

## Decision

1. `PromptVersion` model persists a snapshot of template content with `version_hash` and `is_active` flag.
2. File-based `.j2` templates remain the source of truth for content; DB persistence is a governance overlay.
3. `activate_version()` marks one version as active; `rollback()` reverts to the previous active version.
4. `.render()` loads the active DB version if one exists; falls back to file-based template (backward compatible).
5. `PROMPT_VERSIONING_PERSISTENCE_ENABLED` kill-switch defaults to `False` — file-only behavior until explicitly flipped.

## Consequences

- All existing callers of `.render()` and `.get_template()` see zero behavior change with kill-switch off.
- No A/B testing logic in this batch (deferred).
- Every activation/rollback is written to `apps.audit_log`.
