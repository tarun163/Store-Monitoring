import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'StoreMonitoring.settings')

app = Celery('StoreMonitoring')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# periodic task to run import data every hour
app.conf.beat_schedule = {
    'import_csv_every_hour': {
        'task': 'store.tasks.import_csv_every_hour',
        'schedule': crontab(minute=0, hour='*'),
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request:{self.request!r}')
