# Networkly Project Rename

The repository and Python workspace now use Networkly:

- networkly-monorepo
- networkly-web / networkly_web
- networkly-domain / networkly_domain
- networkly-connectors / networkly_connectors

Imports, Django settings, Docker commands, CI paths, operational scripts,
and documentation use the new package names. Run uv sync --all-packages
after pulling this change. Restart development processes from networkly_web/manage.py.

## Deployment Compatibility

Deploy the code and its updated commands together. Set DJANGO_SETTINGS_MODULE
to networkly_web.settings.production on every existing Render process before
starting the new release. Update any dashboard command overrides that still
refer to the previous package path.

Existing Render resource IDs, database names/users, installed launchd labels,
and historical backup locations keep their existing names. Renaming their
references does not rename those resources and could create replacement
services or lose access to stored data. They require a separate coordinated
infrastructure change. No database schema or user data is renamed here.

The third-party coverage.py testing dependency and ordinary references to test
coverage or banking coverage are unrelated to the old product name.

The developer checkout's absolute directory remains unchanged to avoid breaking
external tools pointing at it. Local configuration is not committed.

## Verification

- Dependency resolution and locked workspace validation passed.
- Django startup and migration-drift checks passed; no migrations required.
- All 12,025 tests collect with the new imports.
- Initial focused regression run: 192 passed.
- Broad four-worker run: 11,377 passed, 45 skipped, 15 failed before the failure limit stopped the run. This is not a full-suite pass.
- Fixed the stale-name branding fixture and an Opportunities search trigger that required unsafe JavaScript evaluation. Follow-up branding and browser role-saving checks: 19 passed.
- Remaining broad-run failures concern schedule copy, the removed Settings sidebar, a loading-animation assertion, and Settings browser tests that expect an immediately visible submit button. These need a separate UI test reconciliation; they are not waived.
- Local marketing, Today, Opportunities, My Applications, Settings, and Assistant pages returned HTTP 200 in WebKit.
