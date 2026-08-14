# Deploying to Vercel + Supabase

Vercel has no release phase, so **migrations never run automatically**. Run them
yourself before the first deploy and after every model change.

## Supabase connection strings

Supabase gives you three. They are not interchangeable:

| Purpose | Host / port | Why |
|---|---|---|
| **The app** | `aws-1-eu-west-1.pooler.supabase.com:6543` | Transaction pooler. Serverless opens a connection per invocation and would otherwise exhaust the database. |
| **Migrations** | `aws-1-eu-west-1.pooler.supabase.com:5432` | Session pooler. DDL needs a stable session, which transaction mode cannot promise. |
| Direct | `db.njhfmeidygekwoedymtc.supabase.co:5432` | IPv6-only unless you buy the IPv4 add-on. Usually not what you want. |

Port `6543` automatically switches Django to pooler-safe behaviour: no persistent
connections, no server-side cursors. Setting `PGBOUNCER_MODE=true` forces the
same on any port.

## Environment variables

Set these in **Vercel → Settings → Environment Variables**, for all environments.

| Variable | Value |
|---|---|
| `SECRET_KEY` | Generate: `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DATABASE_URL` | The **6543** pooler string, with your database password |
| `SUPABASE_S3_ENDPOINT` | `https://njhfmeidygekwoedymtc.storage.supabase.co/storage/v1/s3` |
| `SUPABASE_S3_REGION` | `eu-west-1` |
| `SUPABASE_S3_ACCESS_KEY` | Dashboard → Storage → S3 Connection → new access key |
| `SUPABASE_S3_SECRET_KEY` | Shown once when you create the key above |
| `SUPABASE_S3_BUCKET` | `erp-media` |

You do **not** need `DEBUG` or `ALLOWED_HOSTS`. Settings detects `VERCEL_URL` and
turns `DEBUG` off on its own, and adds both the production and per-deployment
hostnames to `ALLOWED_HOSTS` — preview deployments get a new hostname each time,
so it cannot be hardcoded.

Optional, for password reset to send real mail rather than log it:
`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.

## First deploy

Run these from your machine, using the **5432 session** string:

```bash
export DATABASE_URL="postgresql://postgres.njhfmeidygekwoedymtc:PASSWORD@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
export SECRET_KEY="anything-for-local-admin-tasks"

python manage.py migrate
python manage.py createsuperuser
```

Then seed the three things a fresh database needs. `TenantMiddleware` resolves
anonymous requests via the `default` tenant, so without it even the login page
renders with no tenant attached.

```bash
python manage.py shell -c "
from django.utils import timezone
from datetime import timedelta
from tenants.models import Tenant, User, SubscriptionPlan

tenant, _ = Tenant.objects.get_or_create(
    subdomain='default',
    defaults={
        'name': 'IPELLX',
        'paid_until': timezone.now() + timedelta(days=3650),
        'on_trial': False,
    },
)

u = User.objects.get(username='YOUR_USERNAME')
u.tenant = tenant
u.is_super_admin = True
u.role = 'OWNER'
u.save()

for name, price, days in [('Monthly', 1500, 30), ('Yearly', 15000, 365)]:
    SubscriptionPlan.objects.get_or_create(
        name=name, defaults={'price_kes': price, 'duration_days': days},
    )
"
```

`price_kes`, `duration_days`, and `paid_until` are all required with no
defaults — omitting any of them fails on a not-null constraint.

## After every model change

```bash
python manage.py makemigrations
DATABASE_URL="<the 5432 string>" python manage.py migrate
git add -A && git commit && git push    # Vercel redeploys on push
```

Migrate **before** pushing. Vercel deploys the new code the moment the push
lands, and code expecting a column the database does not have yet will error.

## Known rough edges

- **Uploads** go to Supabase Storage as private objects with 1-hour signed URLs.
  The bucket has a 50 MB file size limit.
- **Long operations** — payroll runs, large CSV exports — are bounded by Vercel's
  function timeout. If reports start timing out, that is the platform, not the
  code.
- **No shell.** There is no Vercel equivalent of `render shell`; every management
  command runs from your machine against the 5432 string.
