# Multi-Channel ERP System - Architecture Update

## Project Separation: Chama as Standalone Service

### Overview

The Chama (Savings Group) module has been successfully separated from the main ERP system as a **standalone Django project**. This allows for independent development, deployment, and scaling of the chama service.

## Directory Structure

```
Multi-Channel ERP System(RealKuku)/
├── 14xlERP_System/              # Main ERP System (Django Project)
│   ├── chama/                   # ⚠️ REMOVED - No longer part of ERP
│   ├── customers/
│   ├── inventory/
│   ├── sales/
│   ├── expenses/
│   ├── dashboard/
│   ├── core/
│   ├── tenants/
│   ├── realkukuERP_System/      # Settings & Configuration
│   └── manage.py
│
├── chama_project/               # NEW: Standalone Chama Service
│   ├── chama/                   # Chama App
│   ├── chama_config/            # Standalone Settings
│   ├── templates/
│   ├── manage.py
│   ├── db.sqlite3              # Separate Database
│   ├── requirements.txt
│   ├── README.md
│   ├── DEPLOYMENT.md
│   └── QUICKSTART.md
│
└── venv/                        # Virtual Environment
```

## Running Both Services

### Prerequisites

- Python 3.10+
- Virtual environment activated
- All dependencies installed

### Start Main ERP System

```bash
cd 14xlERP_System
python manage.py runserver 8000
```

**URL**: http://localhost:8000/

### Start Chama Service (New Terminal)

```bash
cd chama_project
python manage.py runserver 8001
```

**URL**: http://localhost:8001/

## Key Changes

### Main ERP System (14xlERP_System)

1. **Removed from settings.py**:
   - `'chama'` from INSTALLED_APPS

2. **Removed from urls.py**:
   - `path('chama/', include('chama.urls'))`

3. **Removed Directory**:
   - `14xlERP_System/chama/` (archived separately)
   - `chama/migrations/`
   - `chama/templates/chama/`

### Chama Service (New Project)

1. **New Independent Project**:
   - Complete Django project with own settings
   - Separate database (`db.sqlite3`)
   - Own templates and static files

2. **Independent Models**:
   - No `TenantModel` dependency
   - No ERP integration
   - Standalone `Member` model (instead of using `Customer`)

3. **Own Authentication**:
   - Uses Django's built-in User model
   - Separate authentication system
   - Admin interface for data management

## Database Changes

### Main ERP Database
- Location: `14xlERP_System/db.sqlite3`
- **Chama tables REMOVED**:
  - `chama_contribution`
  - `chama_loan`
  - (All chama-related data removed)

### Chama Database
- Location: `chama_project/db.sqlite3`
- **Tables**:
  - `chama_member`
  - `chama_contribution`
  - `chama_loan`
  - `chama_loanpayment`
  - Standard Django tables (auth, admin, etc.)

## Dependency Updates

### Main ERP System
No changes needed - chama dependencies removed from `requirements.txt`

### Chama Service
New `requirements.txt`:
```
Django==6.0.3
djangorestframework==3.14.0
python-decouple==3.8
gunicorn==21.2.0
whitenoise==6.6.0
```

## Migration Commands

### Clean Main ERP

After removing chama from settings, run:

```bash
cd 14xlERP_System
python manage.py migrate
```

This will remove chama tables from the main database.

### Setup Chama Service

```bash
cd chama_project
python manage.py migrate
python manage.py createsuperuser
```

## Admin Access

### Main ERP Admin
- URL: http://localhost:8000/admin/
- Manage: Customers, Inventory, Sales, Expenses, etc.

### Chama Admin
- URL: http://localhost:8001/admin/
- Manage: Members, Contributions, Loans, Payments

## API Integration

### Chama Service API
Available at: http://localhost:8001/api/

Endpoints:
- `GET/POST /api/members/`
- `GET/POST /api/contributions/`
- `GET/POST /api/loans/`
- `GET/POST /api/payments/`

### Connecting ERP to Chama (Optional)

To integrate Chama API with ERP:

```python
# In 14xlERP_System views.py
import requests

CHAMA_API_BASE = 'http://localhost:8001/api'

def get_chama_data():
    response = requests.get(f'{CHAMA_API_BASE}/members/')
    return response.json()
```

## Deployment

### Deploy Main ERP
See: `14xlERP_System/DEPLOYMENT.md`

### Deploy Chama Service
See: `chama_project/DEPLOYMENT.md`

Both can be deployed:
- On same server (different ports)
- On different servers
- On same database server (different databases)

## Troubleshooting

### Main ERP Won't Start After Changes

```bash
# Check if chama is still in settings
grep -n "chama" 14xlERP_System/realkukuERP_System/settings.py

# Check urls.py
grep -n "chama" 14xlERP_System/realkukuERP_System/urls.py

# Remove cache and migrations
rm -rf 14xlERP_System/__pycache__
rm -rf 14xlERP_System/*/migrations/0*.py

# Run migrations fresh
python manage.py migrate
```

### Chama Service Issues

```bash
# Check database
rm chama_project/db.sqlite3

# Recreate everything
python manage.py migrate
python manage.py createsuperuser
```

## Migration Guide (For Old Data)

### Export Chama Data from Main ERP

```bash
# Dump chama data as JSON
cd 14xlERP_System
python manage.py dumpdata chama > chama_data.json
```

### Import to Chama Service

```bash
# Copy data to chama project
cp 14xlERP_System/chama_data.json chama_project/

# Load data into chama database
cd chama_project
python manage.py loaddata chama_data.json
```

## Benefits of Separation

1. **Independent Scaling**: Run multiple chama instances if needed
2. **Separate Concerns**: Chama logic isolated from ERP
3. **Technology Freedom**: Can update chama separately
4. **Team Independence**: Different teams can work on different services
5. **Easier Testing**: Isolated service easier to test
6. **Microservices Ready**: Foundation for microservices architecture

## Future Enhancements

### Planned Features

1. **API Gateway**: Single entry point for both services
2. **Service-to-Service Communication**: Direct database replication for key data
3. **Shared Authentication**: OAuth/JWT between services
4. **Message Queue**: Async communication via Celery/RabbitMQ
5. **Event Bus**: Real-time updates between services

## Support and Questions

For questions about the architecture:
1. Check this file: `ARCHITECTURE.md`
2. Review service-specific docs: `QUICKSTART.md`
3. Contact development team

## Version History

- **v2.0.0** (Current): Chama separated as standalone service
- **v1.x**: Chama integrated as ERP module
