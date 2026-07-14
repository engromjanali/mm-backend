# Mess Management API — Postman examples

Set a Postman environment variable:

```text
base_url = http://127.0.0.1:8000
```

For Vercel, replace it with your deployed URL, for example:

```text
base_url = https://your-project.vercel.app
```

All URLs below use `{{base_url}}`.

## 1. Test API

**GET** `{{base_url}}/`

Expected response:

```text
this is a test api
```

The same test endpoint is also available at **GET** `{{base_url}}/auth/v1/test`.

## 2. Sign up

**POST** `{{base_url}}/auth/v1/sign-up`

Headers:

```text
Content-Type: application/json
```

Body → raw → JSON:

```json
{
  "full_name": "Demo User",
  "email": "demo@example.com",
  "phone": "01700000000",
  "password": "StrongPass!234"
}
```

The API also accepts the example-style names `full-name`, `Phone`, and `Password`.

Save the returned `access_token` as a Postman environment variable named `access_token`.

## 3. Sign in with email

**POST** `{{base_url}}/auth/v1/sign-in`

Headers:

```text
Content-Type: application/json
```

Body:

```json
{
  "type": "email",
  "email": "demo@example.com",
  "password": "StrongPass!234"
}
```

## 4. Sign in with phone

**POST** `{{base_url}}/auth/v1/sign-in`

Body:

```json
{
  "type": "phone",
  "phone": "01700000000",
  "password": "StrongPass!234"
}
```

The API also accepts the compact identifier format:

```json
{
  "type": "phone",
  "email/phone": "01700000000",
  "password": "StrongPass!234"
}
```

## 5. Forget password — email

**POST** `{{base_url}}/auth/v1/forget-password`

Headers:

```text
Content-Type: application/json
```

Body:

```json
{
  "type": "email",
  "email": "demo@example.com"
}
```

The alias **POST** `{{base_url}}/auth/v1/forgot-password` is also available.

## 6. Forget password — phone

**POST** `{{base_url}}/auth/v1/forget-password`

Body:

```json
{
  "type": "phone",
  "phone": "01700000000"
}
```

In development, the OTP is printed in the server terminal when using Django’s console email backend. In production, configure SMTP environment variables so the OTP is delivered by email.

## 7. Change password with OTP

**POST** `{{base_url}}/auth/v1/change-password`

Headers:

```text
Content-Type: application/json
```

Body:

```json
{
  "otp": "123456",
  "password": "NewStrongPass!234"
}
```

Replace `123456` with the six-digit code received by email or shown in the development server terminal. The code expires after 10 minutes and can only be used once.

## 8. Get current profile

**GET** `{{base_url}}/auth/v1/update-profile`

Headers:

```text
Authorization: Bearer {{access_token}}
```

## 9. Update profile without photo

**PATCH** `{{base_url}}/auth/v1/update-profile`

Headers:

```text
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

Body:

```json
{
  "full_name": "Updated Demo User",
  "email": "updated@example.com",
  "phone": "01800000000",
  "address": "Dhaka, Bangladesh",
  "lat": "23.8103000",
  "long": "90.4125000"
}
```

Password is optional during a profile update:

```json
{
  "password": "AnotherStrong!234"
}
```

Changing the password invalidates the previous JWT, so sign in again and save the new `access_token`.

## 10. Update profile with photo

**PATCH** `{{base_url}}/auth/v1/update-profile`

Headers:

```text
Authorization: Bearer {{access_token}}
```

In Postman choose **Body → form-data**. Add these fields:

| Key | Type | Example |
|---|---|---|
| `photo` | File | Select an image |
| `full_name` | Text | Updated Demo User |
| `address` | Text | Dhaka, Bangladesh |
| `lat` | Text | 23.8103000 |
| `long` | Text | 90.4125000 |

Do not manually set `Content-Type` for form-data; Postman adds the required multipart boundary automatically.

## Authentication reminder

Protected profile requests must include:

```text
Authorization: Bearer <access_token>
```

Without this header, the API returns `401 Unauthorized`.
