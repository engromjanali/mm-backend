# Postman API Request Examples

This document outlines how to format your requests in Postman for the Join Request and Notice APIs in the Mess Management System.

---

## Global Headers
For all endpoints below, you **must** include the following headers in Postman:

| Key | Value | Description |
|---|---|---|
| `Authorization` | `Bearer <your_jwt_token>` | JWT Access Token for the authenticated user |
| `Membership-ID` | `1` | The ID of your active MessMemberShip |
| `Session-ID` | `1` | The ID of the active MessSeason |

---

## 1. Join Request List API

### `GET /api/v1/mess/join/list`
Returns a paginated list of join requests for a mess.

**Headers:**
- `Authorization`: `Bearer <token>`

*(Note: Join request list might also use the Membership-ID and Session-ID headers depending on how it was implemented in `MessJoinRequestListView`. Although we didn't add it explicitly to the strict helper requirement in the previous snippet, the global auth is required).*

**Query Parameters (Optional):**
- `limit`: `20` (Number of results per page)
- `offset`: `1` (Page number)
- `status`: `pending`

---

## 2. Notice APIs

### Create Notice
**`POST {base_url}/api/v1/notice/create/`**

**Headers:**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

**Body (raw JSON):**
```json
{
    "title": "Welcome to August Season",
    "content": "Please deposit your initial meal charges by the 5th.",
    "is_pinned": true
}
```

---

### Update Notice
**`PUT {base_url}/api/v1/notice/update/`** (or `PATCH` / `POST`)

**Headers:**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

**Body (raw JSON):**
```json
{
    "notice_id": 1,
    "title": "Welcome to August Season (Updated)",
    "content": "Please deposit your initial meal charges by the 6th now.",
    "is_pinned": false
}
```
*(Alternatively, you can use `{base_url}/api/v1/notice/update/1/` and omit `notice_id` from the body).*

---

### Delete Notice
**`DELETE {base_url}/api/v1/notice/delete/`** (or `POST`)

**Headers:**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

**Body (raw JSON):**
```json
{
    "notice_id": 1
}
```
*(Alternatively, you can use `DELETE {base_url}/api/v1/notice/delete/1/` and omit the body).*

---

### List Notices
**`GET {base_url}/api/v1/notice/list/`**

**Headers:**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

**Query Parameters (Optional):**
- `limit`: `10`
- `offset`: `1`

---

### Get Notice by ID
**`GET {base_url}/api/v1/notice/1/`**

**Headers:**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

---

### Get Pinned Notice
**`GET {base_url}/api/v1/notice/pin/`**

**Headers:**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

---

### Set Pinned Notice
**`POST {base_url}/api/v1/notice/set-pined-notice/`**

**Headers:**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

**Body (raw JSON):**
```json
{
    "notice_id": 5
}
```

---

## 1a. Memberships & Switching

A user can belong to several messes — at most one membership per season. The
membership saved as **current** on their profile decides which mess and season
every `/api/v1/user/...` and `/api/v1/admin/...` endpoint uses. If it's no
longer usable (left or disabled), the newest usable membership becomes current.
Creating a mess or accepting an invite makes the new membership current;
starting a new season moves members from the old season's membership to the new one.
Older seasons stay editable: switch to their membership to work in them.

### Membership Status
**`GET {base_url}/api/v1/user/membership/status`** — `current`, `memberships`
(every mess and season, each with `status` `active|disabled|left`, `is_current`,
`can_switch`, `role`, season dates), `history` (`memberships` without the
current one), `pending_requests` and `invites`.

### Switch Current Membership
**`POST {base_url}/api/v1/user/membership/switch`** `{"membership_id": 12}` →
`200 {"message": "Switched to Green House (July 2026).", "current": {...}}`.
Errors: `404` `Membership not found.`; `400` `You left Green House (July 2026), so it
can't be your current membership.` / `Your membership in … was disabled by its manager.`

Joining a mess you're already in is refused (`You're already a member of Green House.`).

### Invites & Join Requests — the manager picks the season
New members join a **running** season (not ended, not disabled) the manager chooses.
`season_id` is optional; when it's empty the season the manager works in is used.

- **`GET {base_url}/api/v1/admin/member-lookup?query=alice@test.com`** →
  `{"id", "name", "email", "phone", "available", "joined_season_ids": [3]}`: the running
  seasons the user is already in; `available` = there's a running season left to invite them to.
- **`POST {base_url}/api/v1/admin/invites`** `{"user_id": 7, "season_id": 4}` →
  `201 {"id", "invite_code", "status", "user_id", "user_name", "user_email", "season_id": 4, "season_name": "August 2026", ...}`.
- **`POST {base_url}/api/v1/user/invites/accept`** `{"invite_code": "A1B2C3D4"}` joins the
  invite's season → `200 {"message": "Joined Green House (August 2026).", "current": {...}}`.
- **`POST {base_url}/api/v1/admin/join-requests/decision`**
  `{"request_id": 9, "decision": "accepted", "season_id": 4}` →
  `200 {"message": "Alice joined August 2026."}`; the request keeps `season_id` / `season_name`.
  Rejecting needs no `season_id`.

Admin invite and join-request lists, and the user's `invites` / `join_requests` in
`membership/status`, include `season_id` and `season_name` (`null` for a request until it's approved).

Errors (`400`): `{"season_id": "August 2026 has ended. Choose a running season."}` /
`… is disabled. Choose a running season.` / `Season not found in this mess.`;
`{"detail": "Alice is already a member of August 2026."}`; on accept,
`{"detail": "August 2026 has ended. Ask the manager for a new invite."}`.

---

## 1b. My Mess API

### Current Mess Details
**`GET {base_url}/api/v1/user/mess`** — any member, the manager included; scoped to the caller's active season.

**Response `200`:**
```json
{
    "id": 1, "name": "Green House", "address": "Mirpur 10", "email": "", "phone": "",
    "created_at": "2026-07-01T10:00:00Z",
    "season": {"id": 3, "name": "July 2026", "start_date": "2026-07-01", "end_date": null},
    "my_role": "member", "joined_at": "2026-07-03T09:00:00Z",
    "manager": {"user_id": 1, "name": "Manager Mia", "email": "manager@test.com", "phone": "01711111111"},
    "acting_manager": null,
    "members": [{"membership_id": 5, "user_id": 1, "name": "Manager Mia", "role": "manager", "joined_at": "2026-07-01T10:00:00Z"}],
    "stats": {"members": 3, "total_meals": 5.0, "meal_rate": 100.0, "total_cost": 500.0, "total_deposit": 1700.0, "fund_balance": 800.0},
    "permissions": {"can_edit": false, "can_transfer": false, "can_leave": true}
}
```
`members` lists the season's active members (manager, acting manager, then by name).
`stats` cover the active season, except `fund_balance`, which spans every season.
`400` `You are not connected to an active mess.` when the caller has none.

---

## 1c. Member Management APIs (admin)

Scoped to the manager's active season; `<id>` is a `membership_id` from the members list.
Each action returns `200 {"message": "..."}`; errors are `{"detail": "..."}`.

| Endpoint | Who | What |
|---|---|---|
| `GET /api/v1/admin/members?include_disabled=true` | manager / acting manager | Season members; each has `disabled` (members who left are never listed) |
| `POST /api/v1/admin/members/<id>/disable` | manager / acting manager | Member loses access until enabled; records stay. Disabling the acting manager removes that role |
| `POST /api/v1/admin/members/<id>/enable` | manager / acting manager | Gives access back (fails if they joined another mess) |
| `POST /api/v1/admin/members/<id>/acting-manager` | primary manager | Make acting manager (the previous one becomes a member) |
| `DELETE /api/v1/admin/members/<id>/acting-manager` | primary manager | Remove the acting manager role |
| `POST /api/v1/admin/members/<id>/transfer-ownership` | primary manager | Member becomes the primary manager; the caller becomes a regular member |

Rules: you can't disable yourself or the primary manager; leadership goes only to active
members; `404` `Member not found in the current season.`; `403` `Only the primary manager can change the mess leadership.`

---

## 2b. Notice Board APIs (user / admin)

Scoped to the caller's **active season** through their membership (no
`Membership-ID` / `Session-ID` headers). Like deposits and costs, notices belong
to a season, so a new season starts with an empty board. At most one notice per
season is pinned.

Notice shape: `{"id", "title", "description", "pinned", "created_at", "updated_at"}`.

### List Notices
**`GET {base_url}/api/v1/user/notices`** — any member, the manager included.

Returns `{"data": [notice, ...]}`, pinned first, then newest.
`400` `You are not connected to an active mess.` when the caller has none.

### Publish Notice (manager)
**`POST {base_url}/api/v1/admin/notices`**
```json
{"title": "Water off", "description": "No water from 2 to 4 pm.", "pinned": false}
```
`201` with the notice. Title (max 200) and description (max 2000) are trimmed
and required; `pinned: true` unpins the current pinned notice.

### Edit Notice (manager)
**`PATCH {base_url}/api/v1/admin/notices/{id}`** `{"title"?, "description"?}` → `200` notice.

### Pin / Unpin Notice (manager)
**`POST {base_url}/api/v1/admin/notices/{id}/pin`** `{"pinned": true}` → `200` notice.
Pinning unpins any other notice; `409` if another pin wins a race.

### Delete Notice (manager)
**`DELETE {base_url}/api/v1/admin/notices/{id}`** → `200` `{"message": "Notice deleted."}`.

Errors: `403` for non-managers, `404` `Notice not found in the current season. It may have been deleted.`,
`400` field errors such as `{"title": ["Title can't be empty."]}`.

---

## 3. Meal APIs

All meal endpoints are scoped by the two headers below — the mess comes from
`Membership-ID` and the season from `Session-ID`.

**Headers (all meal endpoints):**
- `Authorization`: `Bearer <token>`
- `Membership-ID`: `1`
- `Session-ID`: `1`

**Date format:** `DD-MM-YYYY` (e.g. `10-10-2020`). ISO `YYYY-MM-DD` is also accepted on input; responses always come back as `DD-MM-YYYY`.

**Permissions:** `add` / `update` / `delete` are **Manager / Acting Manager only**.
`list`, `list-all` and `{id}` are open to any active member of the mess.

**Notes:**
- `total_meals` is always derived on the server (`breakfast + lunch + dinner`); sending it is pointless.
- Only one meal row can exist per member per date per season.
- The date must fall inside the season (`start_date` … `end_date`).

---

### Add Meal
**`POST {base_url}/api/v1/meal/add`**

**Body (raw JSON):**
```json
{
    "membership_id": 2,
    "date": "10-10-2020",
    "breakfast": 1,
    "lunch": 2,
    "dinner": 1
}
```
`membership_id` is the member the meal belongs to (any active member of your mess).
`breakfast` / `lunch` / `dinner` default to `0` and must be `0`–`3` in half-meal steps (e.g. `1.5`).

**Response `201`:**
```json
{
    "message": "Meal added successfully.",
    "data": {
        "id": 1,
        "season_id": 1,
        "membership_id": 2,
        "member_name": "Member Moe",
        "member_role": "member",
        "date": "10-10-2020",
        "breakfast": 1,
        "lunch": 2,
        "dinner": 1,
        "total_meals": 4,
        "created_at": "2026-08-14T10:00:00Z",
        "updated_at": "2026-08-14T10:00:00Z"
    }
}
```

---

### Update Meal
**`PUT {base_url}/api/v1/meal/update`** (or `PATCH` / `POST`)

Identify the row **either** by `meal_id` **or** by `membership_id` + `date`.
`POST` and `PATCH` are partial — omitted meal fields keep their current value.

**Body (raw JSON) — by id:**
```json
{
    "meal_id": 1,
    "breakfast": 0,
    "lunch": 1,
    "dinner": 2
}
```

**Body (raw JSON) — by member + date:**
```json
{
    "membership_id": 2,
    "date": "10-10-2020",
    "dinner": 3
}
```
*(You can also use `{base_url}/api/v1/meal/update/1/` and omit `meal_id`.)*

---

### Delete Meal
**`DELETE {base_url}/api/v1/meal/delete`** (or `POST`)

**Body (raw JSON):**
```json
{
    "meal_id": 1
}
```
or
```json
{
    "membership_id": 2,
    "date": "10-10-2020"
}
```
*(You can also use `DELETE {base_url}/api/v1/meal/delete/1/` and omit the body.)*

---

### List My Meals
**`GET {base_url}/api/v1/meal/list`**

Returns only the meals of the membership in the `Membership-ID` header.

**Query Parameters (all optional):**
- `date`: `10-10-2020` — a single day
- `start_date`: `10-10-2020` and/or `end_date`: `20-10-2023` — an inclusive range
- `limit`: `20`, `offset`: `1` (offset is a 1-based page number)

`date` takes precedence over `start_date` / `end_date` when both are sent.

**Examples:**
- `GET /api/v1/meal/list?date=10-10-2020`
- `GET /api/v1/meal/list?start_date=10-10-2020&end_date=20-10-2023`

**Response `200`:**
```json
{
    "total_size": 3,
    "limit": 20,
    "offset": 1,
    "filters": { "start_date": "10-10-2020", "end_date": "20-10-2023" },
    "summary": { "breakfast": 3, "lunch": 3, "dinner": 3, "total_meals": 9 },
    "data": [ { "id": 3, "membership_id": 2, "date": "20-10-2023", "total_meals": 3 } ]
}
```

---

### List All Meals (whole mess)
**`GET {base_url}/api/v1/meal/list-all`**

Same filters as `/list`, but covers every member of the season. Adds a
per-member roll-up computed over the **whole filtered range**, not just the
current page.

**Query Parameters (all optional):**
- `date`, `start_date`, `end_date`, `limit`, `offset` — as above
- `membership_id`: `2` — narrow to a single member

**Examples:**
- `GET /api/v1/meal/list-all?date=10-10-2020`
- `GET /api/v1/meal/list-all?start_date=10-10-2020&end_date=20-10-2023`

**Response `200`:**
```json
{
    "total_size": 4,
    "limit": 20,
    "offset": 1,
    "filters": { "start_date": "10-10-2020", "end_date": "20-10-2023" },
    "summary": { "breakfast": 4, "lunch": 4, "dinner": 4, "total_meals": 12 },
    "member_summary": [
        { "membership_id": 1, "member_name": "Manager Mia", "member_role": "manager",
          "breakfast": 1, "lunch": 1, "dinner": 1, "total_meals": 3 },
        { "membership_id": 2, "member_name": "Member Moe", "member_role": "member",
          "breakfast": 3, "lunch": 3, "dinner": 3, "total_meals": 9 }
    ],
    "data": []
}
```

---

### Get Meal by ID
**`GET {base_url}/api/v1/meal/1/`**

Returns a single meal row from your mess and session, or `404`.

---

## 3b. My Meals API

### List My Meals (active season)
**`GET {base_url}/api/v1/user/meals`**

Any member, the manager included; scoped to the caller's active season (no
`Membership-ID` / `Session-ID` headers). `400` with
`You are not connected to an active mess.` when the caller has none.

**Response `200`:**
```json
{
    "season": {"id": 1, "name": "July 2026"},
    "user_name": "Manager Mia",
    "meal_rate": 100.0,
    "summary": {"total_meals": 3.5, "meal_cost": 350.0, "days": 1},
    "days": [
        {"date": "2026-01-10", "breakfast": 1.0, "lunch": 1.5, "dinner": 1.0, "total": 3.5}
    ]
}
```
`meal_rate` is the whole season's rate (season cost ÷ season meals); `meal_cost` = my meals × rate.

---

## 3c. Admin Meal APIs (manage meals)

Manager / Acting Manager only, scoped to the caller's **active season** (no
`Membership-ID` / `Session-ID` headers). Others get `403`.

- Dates: `YYYY-MM-DD` or `DD-MM-YYYY` on input; `YYYY-MM-DD` in responses.
- `breakfast` / `lunch` / `dinner`: `0`–`3` in half-meal steps; a record needs at least one meal.
- Every response returns the full payload below, so the app refreshes from it.
  Writes add `mutation` and `message`.

### Get Manage-Meals Data
**`GET {base_url}/api/v1/admin/meals`**

**Response `200`:**
```json
{
    "season": {"id": 1, "name": "July 2026"},
    "members": [
        {"id": 2, "name": "Alice", "role": "member", "active": true},
        {"id": 1, "name": "Manager Mia", "role": "manager", "active": true}
    ],
    "meal_rate": 100.0,
    "summary": {"total_meals": 5.0, "total_cost": 500.0, "entries": 2},
    "entries": [
        {"id": 7, "member_id": 1, "member_name": "Manager Mia", "date": "2026-01-10",
         "breakfast": 1.0, "lunch": 1.5, "dinner": 1.0, "total": 3.5}
    ]
}
```
`members` includes the manager and anyone who left but still has meals this season (`active: false` — no new meals for them).
`meal_rate` = season cost ÷ season meals (`0` when there are no meals).

### Add a Day's Meals
**`POST {base_url}/api/v1/admin/meals/bulk`**

```json
{
    "date": "2026-01-10",
    "meals": [
        {"member_id": 1, "breakfast": 1, "lunch": 1.5, "dinner": 1},
        {"member_id": 2, "breakfast": 0, "lunch": 1, "dinner": 0.5}
    ]
}
```
All rows are saved or none. **Response `201`:** payload + `"mutation": {"action": "add", "created_count": 2, "updated_count": 0}`.

Errors:
- `409` — `Meals for 10-01-2026 are already added. Edit them from Manage meals.` (the day already has any meal)
- `400` — date outside the season, future date, empty `meals`, unknown / inactive / duplicate member, invalid or all-zero counts (e.g. `Row 2: Breakfast must be between 0 and 3 meals.`)

### Update a Member's Meal
**`PATCH {base_url}/api/v1/admin/meals`**

```json
{"member_id": 2, "date": "2026-01-10", "dinner": 2.5}
```
Only the sent counts change; the date can't change. `404` if the member has no meal that day, `400` if all counts would become zero (delete instead).

### Delete a Member's Meal
**`DELETE {base_url}/api/v1/admin/meals`**

Body `{"member_id": 2, "date": "2026-01-10"}` or query `?member_id=2&date=2026-01-10`. `404` if there is no such meal.
