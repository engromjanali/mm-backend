# API implementation inventory and follow-up work

Routes below are wired in the current Django URL configuration as of 23 October
2026. This is an implementation inventory, not a guarantee that every deployed
environment has the same code or configuration. Examples are in
[POSTMAN_API_EXAMPLES.md](POSTMAN_API_EXAMPLES.md).

Current APIs use the caller's server-selected context. Admin APIs check manager
or acting-manager permissions; leadership transfers require the primary manager.
Some user routes, such as mess discovery, are public.

## Public app content

| Endpoint | Methods |
|---|---|
| `/api/v1/app/config` | GET |
| `/api/v1/app/pages/<slug:kind>` | GET |
| `/api/v1/app/faqs` | GET |

## Authentication

| Endpoint | Methods |
|---|---|
| `/api/v1/auth/config` | GET |
| `/api/v1/auth/test` | GET |
| `/api/v1/auth/logout` | POST |
| `/api/v1/auth/sign-in` | POST |
| `/api/v1/auth/sign-up` | POST |
| `/api/v1/auth/refresh-token` | POST |
| `/api/v1/auth/forgot-password` | POST |
| `/api/v1/auth/change-password` | POST |
| `/api/v1/auth/profile` | GET |
| `/api/v1/auth/update-profile` | GET / PUT / PATCH |

## User APIs

| Endpoint | Methods |
|---|---|
| `/api/v1/user/account/delete` | POST / DELETE |
| `/api/v1/user/messes` | GET |
| `/api/v1/user/messes/create` | POST |
| `/api/v1/user/membership/status` | GET |
| `/api/v1/user/membership/leave` | POST |
| `/api/v1/user/membership/switch` | POST |
| `/api/v1/user/mess` | GET / PATCH |
| `/api/v1/user/mess/location-search` | GET |
| `/api/v1/user/join-requests` | POST / DELETE |
| `/api/v1/user/join-requests/<int:pk>` | POST / DELETE |
| `/api/v1/user/invites/accept` | POST |
| `/api/v1/user/invites/decline` | POST |
| `/api/v1/user/notices/<int:pk>` | GET |
| `/api/v1/user/notices` | GET |
| `/api/v1/user/opinions` | GET |
| `/api/v1/user/opinions/<int:pk>/messages` | GET / POST |
| `/api/v1/user/deposits` | GET |
| `/api/v1/user/funds` | GET |
| `/api/v1/user/costs` | GET |
| `/api/v1/user/meals` | GET |

## Manager APIs

| Endpoint | Methods |
|---|---|
| `/api/v1/admin/member-lookup` | GET |
| `/api/v1/admin/invites` | GET / POST / DELETE |
| `/api/v1/admin/join-requests` | GET |
| `/api/v1/admin/join-requests/decision` | POST |
| `/api/v1/admin/members` | GET |
| `/api/v1/admin/members/<int:pk>/disable` | POST |
| `/api/v1/admin/members/<int:pk>/enable` | POST |
| `/api/v1/admin/members/<int:pk>/acting-manager` | POST / DELETE |
| `/api/v1/admin/members/<int:pk>/transfer-ownership` | POST |
| `/api/v1/admin/seasons` | GET / POST |
| `/api/v1/admin/seasons/auto-create` | GET / PUT |
| `/api/v1/admin/seasons/<int:pk>` | PATCH / DELETE |
| `/api/v1/admin/seasons/<int:pk>/end` | POST |
| `/api/v1/admin/seasons/<int:pk>/disable` | POST |
| `/api/v1/admin/seasons/<int:pk>/enable` | POST |
| `/api/v1/admin/seasons/<int:pk>/switch` | POST |
| `/api/v1/admin/notices` | POST |
| `/api/v1/admin/notices/<int:pk>` | PATCH / DELETE |
| `/api/v1/admin/notices/<int:pk>/pin` | POST |
| `/api/v1/admin/opinions` | POST |
| `/api/v1/admin/opinions/<int:pk>` | PATCH |
| `/api/v1/admin/opinions/<int:pk>/publish` | POST |
| `/api/v1/admin/deposits` | GET / POST |
| `/api/v1/admin/deposits/summary` | GET |
| `/api/v1/admin/deposits/<int:pk>` | PATCH / DELETE |
| `/api/v1/admin/funds` | POST |
| `/api/v1/admin/funds/<int:pk>` | PATCH / DELETE |
| `/api/v1/admin/costs` | POST |
| `/api/v1/admin/costs/<int:pk>` | PATCH / DELETE |
| `/api/v1/admin/meals` | GET / PATCH / DELETE |
| `/api/v1/admin/meals/bulk` | POST |

## Scheduled jobs

| Endpoint | Methods |
|---|---|
| `/api/v1/cron/expire-invites-and-requests` | GET |
| `/api/v1/cron/create-scheduled-seasons` | GET |

## Compatibility routes

Legacy `/api/v1/mess/`, `/api/v1/notice/`, and `/api/v1/meal/` routes remain mounted.
Their older header/payload conventions differ from the APIs above. Empty legacy
cost/deposit/fund URL modules do not make the previously proposed endpoints
implemented; use the current user/admin routes.

## Follow-up work

- Server-side JWT/session revocation on logout, when session invalidation is required.
  Logout currently acknowledges the request and the app clears its local tokens.
- Authentication/password-reset rate limiting and abuse protection.
- Pagination and incremental loading for growing notice lists.
- Deployment checks for SMTP delivery, persistent uploads, and scheduled jobs.

Personal Home totals (`my_stats`) and a mess-scoped single-notice endpoint are
implemented. Notices persist across seasons; funds carry across seasons, while
meals, deposits, and costs are scoped to the selected season.
