# Vercel deployment

Vercel detects this Django project from `manage.py`; this repository uses automatic Django routing and keeps cron schedules in `vercel.json`. See the [official Django deployment guide](https://vercel.com/docs/frameworks/full-stack/django).

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

If Vercel logs `Cannot assign requested address` and shows an IPv6 database address, replace the deployed `DATABASE_URL`. For Supabase, copy the **Session pooler** or **Transaction pooler** connection string from the Supabase dashboard. Use the exact hostname and port supplied for the chosen pooler mode. Do not use the direct `db.<project>.supabase.co:5432` URL from Vercel when that hostname resolves only to IPv6. Update the Vercel variable for every environment and redeploy.

For a custom API domain, also add:

- `DJANGO_ALLOWED_HOSTS=api.example.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://api.example.com`

Do not enable `DJANGO_DEBUG` in production.

To deliver password-reset codes, configure the `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `EMAIL_HOST_USER`, and `EMAIL_HOST_PASSWORD` variables shown in `.env.example`. The default console backend writes emails to logs instead of delivering them. Production must use the SMTP backend with valid credentials. Set `DEFAULT_FROM_EMAIL` to the actual sender address in Vercel; do not assume dashboard values expand `${EMAIL_HOST_USER}`.

For SMTP, port `587` uses `EMAIL_USE_TLS=True` and `EMAIL_USE_SSL=False`; port `465` uses the reverse. `EMAIL_TIMEOUT=20` bounds socket waits, not the total request duration. Gmail requires an app password for the configured account. Delivery failures return a handled `503`; do not log reset codes in production.

## Scheduled jobs (Vercel Cron)

`vercel.json` schedules the nightly jobs. Vercel runs crons in UTC:

| Job | Path | Schedule (UTC) | Bangladesh time |
|---|---|---|---|
| Expire invitations and join requests pending for 7 days | `/api/v1/cron/expire-invites-and-requests` | `30 17 * * *` | 11:30 PM |
| Auto-create seasons due today (and switch their members) | `/api/v1/cron/create-scheduled-seasons` | `5 18 * * *` | 12:05 AM |

Add a `CRON_SECRET` environment variable (a long random string). Vercel sends it as `Authorization: Bearer <CRON_SECRET>`; without it the cron endpoints refuse every call. Crons run only on the production deployment. Hobby cron timing is not exact; check the [current scheduling limits](https://vercel.com/docs/cron-jobs/usage-and-pricing) when timing matters.

Jobs use the date in `MESS_TIME_ZONE` (default `Asia/Dhaka`), not UTC, so a season created at 12:05 AM starts on that Bangladesh date. Running a job again the same day is safe.

To run a job by hand: `venv/bin/python manage.py expire_invites_and_requests` or `venv/bin/python manage.py create_scheduled_seasons`.

## Database migrations

Run migrations against the production database once and after every deployment that adds migrations:

```bash
# Load production environment variables securely before running this command.
venv/bin/python manage.py migrate
```

Then redeploy the project. The root URL should respond with `this is a test api`, and the authentication test URL is `/api/v1/auth/test`.

## Uploaded profile photos

The backend already selects Cloudinary storage when all three variables are set:

- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

Without them, it falls back to local media storage, which is unsuitable for
persistent uploads on Vercel. PostgreSQL stores the photo reference, not its bytes.
Use the placeholders in [.env.example](.env.example) as a configuration checklist;
never commit production credentials. Deploy backend API additions before the
frontend version that depends on them.
