import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Copy the live SQLite database into a timestamped backup, and prune old backups."

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=30,
            help='Number of most recent backups to keep (default: 30).',
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES['default']['NAME'])
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(f"No database found at {db_path}"))
            return

        backup_dir = db_path.parent / 'backups'
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f"db_{timestamp}.sqlite3"
        shutil.copy2(db_path, backup_path)
        self.stdout.write(self.style.SUCCESS(f"Backed up to {backup_path}"))

        # Prune old backups beyond --keep
        keep = options['keep']
        backups = sorted(backup_dir.glob('db_*.sqlite3'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[keep:]:
            old.unlink()
            self.stdout.write(f"Removed old backup {old.name}")
