# Mess Management System — API Roadmap

## 1. AuthManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/auth/sign-up` | POST | ✅ Done |
| `/api/v1/auth/sign-in` | POST | ✅ Done |
| `/api/v1/auth/refresh-token` | POST | ✅ Done |
| `/api/v1/auth/forgot-password` | POST | ✅ Done |
| `/api/v1/auth/change-password` | POST | ✅ Done |
| `/api/v1/auth/profile` | GET | ✅ Done |
| `/api/v1/auth/update-profile` | GET / PUT / PATCH | ✅ Done |
| `/api/v1/auth/config` | GET | ✅ Done |

---

## 2. MessManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/mess/create/` | POST | ✅ Done |
| `/api/v1/mess/list` | GET | ✅ Done |
| `/api/v1/mess/join/` | POST | ✅ Done |
| `/api/v1/mess/<id>/` | GET | 🔲 Planned |
| `/api/v1/mess/<id>/update/` | PUT / PATCH | 🔲 Planned |
| `/api/v1/mess/<id>/seasons/` | GET / POST | 🔲 Planned |
| `/api/v1/mess/<id>/members/` | GET | 🔲 Planned |
| `/api/v1/mess/<id>/membership-requests/` | GET / POST | 🔲 Planned |
| `/api/v1/mess/<id>/invitations/` | GET / POST | 🔲 Planned |

---

## 2a. Membership (user / admin)
Manager & acting manager are stored on `Mess`; a member's role is derived from it. Users join a mess only through a membership in its active season.

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/user/messes` (public) | GET | ✅ Done |
| `/api/v1/user/messes/create` | POST | ✅ Done |
| `/api/v1/user/membership/status` | GET | ✅ Done |
| `/api/v1/user/membership/leave` | POST | ✅ Done |
| `/api/v1/user/join-requests` | POST | ✅ Done |
| `/api/v1/user/join-requests/<id>` | DELETE | ✅ Done |
| `/api/v1/user/invites/accept` | POST | ✅ Done |
| `/api/v1/user/invites/decline` | POST | ✅ Done |
| `/api/v1/admin/member-lookup` | GET | ✅ Done |
| `/api/v1/admin/invites` | GET / POST / DELETE | ✅ Done |
| `/api/v1/admin/join-requests` | GET | ✅ Done |
| `/api/v1/admin/join-requests/decision` | POST | ✅ Done |
| `/api/v1/admin/members` | GET | ✅ Done |
| `/api/v1/admin/seasons` | GET / POST (new season, carries members) | ✅ Done |
| `/api/v1/admin/mess` (details / update) | GET / PATCH | 🔲 Planned |
| `/api/v1/admin/mess/leadership` (transfer manager) | POST | 🔲 Planned |

---

## 2b. Deposits (active season)
Positive `amount` = credit, negative = debit. A manager is also a member, so they appear in member lists/totals and have their own deposits.

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/user/deposits` (my deposits + totals) | GET | ✅ Done |
| `/api/v1/admin/deposits?member_id=&date=&start=&end=` | GET / POST | ✅ Done |
| `/api/v1/admin/deposits/<id>` | PATCH / DELETE | ✅ Done |
| `/api/v1/admin/deposits/summary` (mess totals, member balances, mine) | GET | ✅ Done |

---

## 2c. Funds (whole mess)
Shared mess money, not tied to a member. Belongs to the mess, not a season — it carries over when a new season starts. Positive `amount` = credit, negative = debit. Every member (manager included) reads; only the manager / acting manager writes.

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/user/funds?date=&start_date=&end_date=` (list + totals + overall `balance`) | GET | ✅ Done |
| `/api/v1/admin/funds` | POST | ✅ Done |
| `/api/v1/admin/funds/<id>` | PATCH / DELETE | ✅ Done |

---

## 3. NoticeManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/notice/create` | POST | ✅ Done |
| `/api/v1/notice/update` | PUT / PATCH / POST | ✅ Done |
| `/api/v1/notice/delete` | DELETE / POST | ✅ Done |
| `/api/v1/notice/list` | GET | ✅ Done |
| `/api/v1/notice/{id}` | GET | ✅ Done |
| `/api/v1/notice/pin` | GET | ✅ Done |
| `/api/v1/notice/set-pined-notice` | POST | ✅ Done |

---

## 3. MealManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/meal/add` | POST | ✅ Done |
| `/api/v1/meal/update` | PUT / PATCH / POST | ✅ Done |
| `/api/v1/meal/delete` | DELETE / POST | ✅ Done |
| `/api/v1/meal/list` | GET | ✅ Done |
| `/api/v1/meal/list-all` | GET | ✅ Done |
| `/api/v1/meal/{id}` | GET | ✅ Done |

Writes (`add` / `update` / `delete`) are Manager / Acting Manager only.
`list` returns the caller's own meals; `list-all` returns every member's.
Both accept `?date=DD-MM-YYYY` or `?start_date=…&end_date=…`.

---

## 4. CostManagement (active season)
A shopping (bazar) entry: the member who shopped, date + time, and product / price rows; its total is the sum of the prices. Every member (manager included) reads; only the manager / acting manager writes. A new season starts with an empty list.

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/user/costs` (season + list + totals) | GET | ✅ Done |
| `/api/v1/admin/costs` | POST | ✅ Done |
| `/api/v1/admin/costs/<id>` (`items` replaces every product) | PATCH / DELETE | ✅ Done |

---

## 5. DepositManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/deposit/create/` | POST | 🔲 Planned |
| `/api/v1/deposit/<id>/` | GET / PUT / DELETE | 🔲 Planned |
| `/api/v1/deposit/season/<season_id>/` | GET | 🔲 Planned |

---

## 6. FundManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/fund/overview/` | GET | 🔲 Planned |
| `/api/v1/fund/breakdown/` | GET / POST | 🔲 Planned |
