# Vercel deployment

Vercel detects this Django project from `manage.py`; custom build and rewrite rules are not required.

## Project settings

In the Vercel project settings:

1. Set **Root Directory** to the directory containing `manage.py`. If the Git repository opens directly in this directory, leave Root Directory empty.
2. Do not set an Output Directory.
3. Keep Framework Preset on Django or automatic detection.

## Environment variables

Add these variables for Production and Preview deployments:

- `DJANGO_SECRET_KEY`: a long, random, stable secret. Do not change it after users receive JWTs.
- `DATABASE_URL`: the PostgreSQL connection URL, including `sslmode=require` when the provider requires TLS.

The variable names must be added in the Vercel dashboard under **Project Settings → Environment Variables** (or with `vercel env add`); your local `.env` file is ignored by Git and is not deployed. `SECRET_KEY` is accepted as an alias, but `DJANGO_SECRET_KEY` is recommended.

If Vercel logs `Cannot assign requested address` and shows an IPv6 database address, replace the deployed `DATABASE_URL`. For Supabase, copy the **Season pooler** or **Transaction pooler** connection string from the Supabase dashboard. It normally uses `*.pooler.supabase.com` on port `6543`. Do not use the direct `db.<project>.supabase.co:5432` URL from Vercel when that hostname resolves only to IPv6. Update the Vercel variable for every environment and redeploy.

For a custom API domain, also add:

- `DJANGO_ALLOWED_HOSTS=api.example.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://api.example.com`

Do not enable `DJANGO_DEBUG` in production.

To deliver password-reset codes, configure the `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, and `EMAIL_HOST_PASSWORD` variables shown in `.env.example`. Without them, emails are written only to function logs.

## Database migrations

Run migrations against the production database once and after every deployment that adds migrations:

```bash
DATABASE_URL='your-production-url' DJANGO_SECRET_KEY='your-production-secret' venv/bin/python manage.py migrate
```

Then redeploy the project. The root URL should respond with `this is a test api`, and the authentication test URL is `/auth/v1/test`.

## Uploaded profile photos

Vercel Functions do not provide persistent writable storage. Before using profile-photo uploads in production, configure a Django storage backend backed by an object-storage service. PostgreSQL stores the photo path, not the photo file itself.
