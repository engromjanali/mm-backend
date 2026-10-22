# Postman API examples

These examples use the current APIs called by Mess Pilot. Set a Postman
`base_url` variable, such as `http://127.0.0.1:8000`, and keep `access_token` and
`refresh_token` in a private environment. Do not export real credentials.

Use `Authorization: Bearer {{access_token}}` on authenticated requests and
`Content-Type: application/json` for JSON bodies. Current `/api/v1/user/...` and
`/api/v1/admin/...` routes resolve the caller's selected mess/season on the server;
they do not require `Membership-ID` or `Session-ID` headers.

Use IDs returned by your own requests. Sample IDs and dates below are illustrative;
meal dates must be within a writable season and must not be in the future.
See [roadmap.md](roadmap.md) for the route/method inventory.

## Authentication

### Sign in

`POST {{base_url}}/api/v1/auth/sign-in` (no authorization required):

```json
{"type": "email", "email": "member@example.com", "password": "your-password"}
```

Phone sign-in uses `"type": "phone"` and `"phone"` instead of `"email"`.
The response contains `access_token`, `refresh_token`, `token_type`, `expires_in`,
`refresh_expires_in`, and `user`. Save the returned tokens in your private environment.

### Refresh tokens

`POST {{base_url}}/api/v1/auth/refresh-token`:

```json
{"refresh_token": "{{refresh_token}}"}
```

No access-token header is required. Replace both saved tokens with the response.

### Logout

`POST {{base_url}}/api/v1/auth/logout` with access-token authorization, no body.
Returns `200` and a message. The client clears its tokens; this endpoint currently
does not revoke stateless JWTs on the server.

### Password reset

`POST {{base_url}}/api/v1/auth/forgot-password`:

```json
{"type": "email", "email": "member@example.com"}
```

Use the delivered code with `POST {{base_url}}/api/v1/auth/change-password`:

```json
{"otp": "123456", "password": "your-new-password"}
```

Codes expire after the configured lifetime and are single use. A mail-delivery
failure returns `503`; see [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md) for SMTP setup.

## Memberships and current context

`GET {{base_url}}/api/v1/user/membership/status` returns `current`, `memberships`,
`history`, `pending_requests`, and `invites`. Membership summaries include roles,
season details, `is_current`, and `can_switch`. Leaders can have season access
without a personal membership; don't assume every summary has a membership ID.

Switch with `POST {{base_url}}/api/v1/user/membership/switch`:

```json
{"membership_id": 12}
```

Leader-only access can use `{"mess_id": 1, "season_id": 3}` instead.
Older/left memberships may be selected for historical access; this does not grant
permission to write new records. Disabled seasons cannot be selected, and a
regular member cannot select a disabled membership.

### Invitations and requests

- `GET {{base_url}}/api/v1/admin/member-lookup?query=member@example.com`
- `POST {{base_url}}/api/v1/admin/invites` with `{"user_id": 7, "season_id": 4}`.
- `POST {{base_url}}/api/v1/user/invites/accept` with `{"invite_code": "A1B2C3D4"}`.
- `GET {{base_url}}/api/v1/admin/join-requests` to list requests.
- `POST {{base_url}}/api/v1/admin/join-requests/decision` with
  `{"request_id": 9, "decision": "accepted", "season_id": 4}`.

The manager chooses a running season for an invitation or accepted request.
`season_id` can be omitted when the selected season is suitable. Rejection does
not need a season ID. The API checks membership, season state, and role permissions.

## Current mess and Home totals

`GET {{base_url}}/api/v1/user/mess` returns the selected mess, season, leadership,
members, permissions, aggregate `stats`, and the caller's `my_stats`:

```json
{
  "my_stats": {"meal": 1.5, "deposit": 1700.0, "remaining": 1550.0},
  "stats": {
    "members": 3,
    "total_meals": 5.0,
    "meal_rate": 100.0,
    "total_cost": 500.0,
    "total_deposit": 1700.0,
    "fund_balance": 800.0
  }
}
```

This is a response excerpt. `member_stats` is manager/acting-manager only;
`my_stats` describes the caller and is available to members too. Without a
personal membership, personal values are zero. Fund balance spans seasons.
Managers can `PATCH` the same mess endpoint to update permitted details.

## Member management

`<id>` below is a membership ID from the selected season.

| Request | Action |
|---|---|
| `GET /api/v1/admin/members?include_disabled=true&include_left=true` | List members with the requested status filters |
| `POST /api/v1/admin/members/<id>/disable` | Disable access |
| `POST /api/v1/admin/members/<id>/enable` | Enable access |
| `POST /api/v1/admin/members/<id>/acting-manager` | Assign acting manager |
| `DELETE /api/v1/admin/members/<id>/acting-manager` | Remove acting manager |
| `POST /api/v1/admin/members/<id>/transfer-ownership` | Transfer primary leadership |

Leadership changes require the primary manager. Member status changes also check
that the caller is allowed to manage the selected season.

## Notices

Notices belong to a **mess**, persist across its seasons, and have at most one
pinned notice per mess. Current requests use `description` and `pinned`.

- `GET {{base_url}}/api/v1/user/notices` returns `{"data": [...]}`, pinned first.
- `GET {{base_url}}/api/v1/user/notices/1` returns one notice from the caller's mess.
  An absent notice or a notice from another mess returns `404`.

Publish with `POST {{base_url}}/api/v1/admin/notices`:

```json
{"title": "Water off", "description": "No water from 2 to 4 pm.", "pinned": false}
```

Title and description are trimmed and required. Their limits are 200 and 2000
characters respectively. The `201` response includes `id`, `title`, `description`,
`pinned`, `created_at`, and `updated_at`.

- `PATCH /api/v1/admin/notices/1` with `{"title": "Updated notice"}`.
- `POST /api/v1/admin/notices/1/pin` with `{"pinned": true}`.
- `DELETE /api/v1/admin/notices/1` deletes the notice.

Writes require manager/acting-manager access. Pinning replaces the previous pin;
a concurrent pin conflict can return `409`.

## Meals

`GET {{base_url}}/api/v1/user/meals` returns the caller's meals, selected season,
meal rate, summary, and day records. Managers with a personal membership also have
personal meal data.

`GET {{base_url}}/api/v1/admin/meals` returns members, meal entries, meal rate, and
mess summary. Dates use `YYYY-MM-DD` in responses; counts use half-meal steps
between 0 and 3 for each breakfast/lunch/dinner value.

Add a day with `POST {{base_url}}/api/v1/admin/meals/bulk`:

```json
{
  "date": "2026-07-10",
  "meals": [
    {"member_id": 1, "breakfast": 1, "lunch": 1.5, "dinner": 1},
    {"member_id": 2, "breakfast": 0, "lunch": 1, "dinner": 0.5}
  ]
}
```

All rows save together or none do. An already-added day returns `409`.
Update with `PATCH /api/v1/admin/meals` and
`{"member_id": 2, "date": "2026-07-10", "dinner": 2.5}`.
Delete with `DELETE /api/v1/admin/meals` and
`{"member_id": 2, "date": "2026-07-10"}`.
Server checks season dates, membership, writable status, and nonzero meal totals.

## Other current APIs

Deposits and costs are season-scoped; funds belong to the mess and carry across
seasons. The current route inventory, including seasons, opinions, account
deletion, and public app content, is in [roadmap.md](roadmap.md).

## Legacy routes

The backend still mounts `/api/v1/mess/`, `/api/v1/notice/`, and `/api/v1/meal/`
compatibility routes. Their payload/header contracts differ from the current
user/admin APIs. Consult `MessManagement/notice_urls.py`, `MessManagement/views.py`,
and `MealManagement/urls.py` when maintaining older clients. New app flows should
use the current routes above; there is no `/api/v1/mess/join/list` route.
