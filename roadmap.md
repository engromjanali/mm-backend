# Mess Management System — API Roadmap

## 1. AuthManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/auth/sign-up` | POST | ✅ Done |
| `/api/v1/auth/sign-in` | POST | ✅ Done |
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
| `/api/v1/meal/create/` | POST | 🔲 Planned |
| `/api/v1/meal/<id>/` | GET / PUT / DELETE | 🔲 Planned |
| `/api/v1/meal/season/<season_id>/` | GET | 🔲 Planned |

---

## 4. CostManagement
| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/cost/create/` | POST | 🔲 Planned |
| `/api/v1/cost/<id>/` | GET / PUT / DELETE | 🔲 Planned |
| `/api/v1/cost/season/<season_id>/` | GET | 🔲 Planned |

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
