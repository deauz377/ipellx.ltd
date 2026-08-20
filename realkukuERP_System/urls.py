"""
URL configuration for 14xlevel ERP project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.views.static import serve

from sales.views import cron_send_payment_reminders
from core.views import admin_run_migrations

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('dashboard.urls')),
    path('inventory/', include('inventory.urls')),
    path('sales/', include('sales.urls')),
    path('customers/', include('customers.urls')),
    path('expenses/', include('expenses.urls')),
    path('payroll/', include('payroll.urls')),
    path('hr/', include('hr.urls')),
    path('accounting/', include('accounting.urls')),
    path('budgeting/', include('budgeting.urls')),
    # Unauthenticated customer-facing payment page -- secured by the
    # unguessable token in the URL itself, not a login. See
    # core.middleware.EXEMPT_PREFIXES and sales/views_public.py.
    path('pay/', include('sales.urls_public')),
    # Vercel Cron target -- authenticates via CRON_SECRET, not a login.
    path('cron/send-payment-reminders/', cron_send_payment_reminders, name='cron_send_payment_reminders'),
    # Ops: trigger `migrate` on this deployment's own database without ever
    # needing DATABASE_URL outside Vercel's own environment. Same CRON_SECRET.
    path('cron/migrate/', admin_run_migrations, name='admin_run_migrations'),
]

# WhiteNoise serves STATIC_ROOT but not user uploads, so when files live on a
# local disk they need routing through Django itself. With Supabase Storage the
# file URLs are signed links to the bucket and never reach this app, so the
# route would only point at a directory that does not exist.
if settings.STORAGES['default']['BACKEND'].endswith('FileSystemStorage'):
    urlpatterns += [
        path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
