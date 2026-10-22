# Local project instructions

## API structure

- `/api/v1/user/...` — endpoints for regular users (members)
- `/api/v1/admin/...` — endpoints for admins (mess managers)

Put new or changed endpoints under the prefix that matches who calls them, and keep the Flutter app's endpoint constants (`mess-management/lib/config/util/app_constants.dart`) in sync.

## Code organization

- Keep code in the matching Django app. Current user/admin routes use `user_urls.py` and `admin_urls.py`; public/auth routes use their existing URL modules. Views and tests may be split by feature (`notice_views.py`, `season_views.py`, `test_*.py`); shared helpers go in the app's `utils.py`.
- In `views.py`, user views come before admin views, each group under a section comment.
- One migration per logical change, with a descriptive `--name`.
- Put new code in the section it belongs to; when a file you touch is disorganized, tidy the related part and point out the rest.

## Error handling

The Flutter app shows backend error messages to the user as-is, so every error must be specific and readable.

- Raise `ValidationError({"field": "..."})` for field problems and `{"detail": "..."}` / `NotFound` / `PermissionDenied` for the rest — shapes the app already parses (`detail`, `message`, `non_field_errors`, `{field: [...]}`).
- Never let an unexpected exception become a bare 500 or HTML page, and never return tracebacks, SQL, tokens or other internals.

## Roles: the manager is also a member

A manager / acting manager may have their own season membership and personal totals. Include their real membership in member lists and let user ("my …") endpoints work for them. Leaders can also access historical seasons without a personal membership; do not fabricate a `MessMemberShip` or personal financial records for that context.
