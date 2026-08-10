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
