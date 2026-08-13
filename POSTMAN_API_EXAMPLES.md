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
`breakfast` / `lunch` / `dinner` default to `0` and must be `>= 0`.

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
