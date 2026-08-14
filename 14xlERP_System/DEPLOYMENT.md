# 14XL ERP System - Production Deployment Guide

## Prerequisites
- Python 3.8+
- PostgreSQL (recommended for production)
- Nginx (for serving static files)
- Gunicorn (WSGI server)
- SSL certificate (Let's Encrypt recommended)

## 1. Server Setup

### Update system packages
```bash
sudo apt update && sudo apt upgrade -y
```

### Install required packages
```bash
sudo apt install python3 python3-pip postgresql postgresql-contrib nginx curl -y
```

### Install Python virtual environment
```bash
sudo apt install python3-venv -y
```

## 2. Database Setup

### Create PostgreSQL database
```bash
sudo -u postgres psql
CREATE DATABASE 14xl_erp;
CREATE USER erp_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE 14xl_erp TO erp_user;
\q
```

## 3. Application Deployment

### Clone and setup application
```bash
cd /var/www
sudo mkdir 14xl_erp
sudo chown -R $USER:$USER 14xlevel_erp
cd 14xlevel_erp

# Copy your project files here
# git clone https://github.com/your-repo/14xlevel-erp.git .
```

### Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Install dependencies
```bash
pip install -r requirements.txt
pip install gunicorn psycopg2-binary django-environ
```

### Environment configuration
Create `.env` file:
```bash
DEBUG=False
SECRET_KEY=your-very-secure-secret-key-here
DATABASE_URL=postgresql://erp_user:your_secure_password@localhost:5432/14xlevel_erp
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
```

### Database migration
```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

### Create superuser
```bash
python manage.py createsuperuser
```

## 4. Gunicorn Setup

### Create Gunicorn service
```bash
sudo nano /etc/systemd/system/gunicorn.service
```

Add this content:
```ini
[Unit]
Description=gunicorn daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/14xlevel_erp
ExecStart=/var/www/14xlevel_erp/venv/bin/gunicorn --access-logfile - --workers 3 --bind unix:/var/www/14xlevel_erp/14xlevel_erp.sock realkukuERP_System.wsgi:application

[Install]
WantedBy=multi-user.target
```

### Start Gunicorn service
```bash
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
sudo systemctl status gunicorn
```

## 5. Nginx Configuration

### Create Nginx site configuration
```bash
sudo nano /etc/nginx/sites-available/14xlevel_erp
```

Add this content:
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /var/www/14xlevel_erp/static/;
    }

    location /media/ {
        alias /var/www/14xlevel_erp/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/14xlevel_erp/14xlevel_erp.sock;
    }
}
```

### Enable site and restart Nginx
```bash
sudo ln -s /etc/nginx/sites-available/14xlevel_erp /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

## 6. SSL Certificate (Let's Encrypt)

### Install Certbot
```bash
sudo apt install snapd -y
sudo snap install core; sudo snap refresh core
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
```

### Get SSL certificate
```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## 7. Security Hardening

### Configure firewall
```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
```

### Secure PostgreSQL
```bash
sudo nano /etc/postgresql/12/main/pg_hba.conf
# Change local connections to require password
local   all             all                                     md5
```

### Regular backups
Create backup script `/var/www/14xlevel_erp/backup.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/var/www/backups"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U erp_user -h localhost 14xlevel_erp > $BACKUP_DIR/14xlevel_erp_$DATE.sql
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
```

Make executable and add to cron:
```bash
chmod +x /var/www/14xlevel_erp/backup.sh
crontab -e
# Add: 0 2 * * * /var/www/14xlevel_erp/backup.sh
```

## 8. Monitoring

### Install monitoring tools
```bash
sudo apt install htop iotop -y
```

### Log rotation
```bash
sudo nano /etc/logrotate.d/14xlevel_erp
/var/www/14xlevel_erp/logs/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 www-data www-data
}
```

## 9. Performance Optimization

### Database optimization
```sql
-- In PostgreSQL
CREATE INDEX CONCURRENTLY idx_invoice_date ON sales_invoice(date);
CREATE INDEX CONCURRENTLY idx_product_sku ON inventory_product(sku);
```

### Caching (optional)
Add to settings.py:
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/',
    }
}
```

## 10. Maintenance

### Update procedure
```bash
cd /var/www/14xl_erp
source venv/bin/activate
git pull origin main
pip install -r requirements.txt --upgrade
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
```

## Access Your Application

Your 14XL ERP System is now live at: `https://your-domain.com`

Default admin login: Use the superuser credentials you created during setup.

## Troubleshooting

### Common issues:
1. **Permission errors**: Check file ownership (`chown -R www-data:www-data /var/www/14xl_erp`)
2. **Database connection**: Verify PostgreSQL credentials in .env file
3. **Static files not loading**: Run `python manage.py collectstatic`
4. **502 Bad Gateway**: Check Gunicorn service status (`sudo systemctl status gunicorn`)

For support, check the application logs:
```bash
sudo journalctl -u gunicorn -f
sudo tail -f /var/log/nginx/error.log
```