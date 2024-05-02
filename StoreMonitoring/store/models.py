from django.db import models
import uuid

# common Base model
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# model to store store_id and timezone
class StoreData(BaseModel):
    store_id = models.CharField(max_length=50, unique=True)
    timezone_str = models.CharField(max_length=50, default='America/Chicago')  # Default timezone

    def __str__(self):
        return self.store_id
    
# model to store activity 
class StoreActivity(BaseModel):
    store = models.ForeignKey(StoreData, on_delete=models.CASCADE)
    timestamp_utc = models.DateTimeField()
    timestamp_local = models.DateTimeField() # local time referance of storedata model
    status = models.CharField(max_length=10)  # 'active' or 'inactive'

    def __str__(self):
        return f"{self.store.store_id} - {self.timestamp_utc} - {self.status}"
    
# model to store business hours in local time
class BusinessHours(BaseModel):
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    store = models.ForeignKey(StoreData, on_delete=models.CASCADE)
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time_local = models.TimeField()
    end_time_local = models.TimeField()

    def __str__(self):
        return f"{self.store.store_id} - {self.get_day_of_week_display()} - {self.start_time_local} to {self.end_time_local}"

# model to store reports
class Report(BaseModel):
    ReportStatus = [
        ('Running', 'RUNNING'), 
        ('Complete', 'COMPLETE'),
    ]
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to='store/results/', max_length=100)  # Store CSV data as file
    status = models.CharField(choices=ReportStatus, default='Running')

    def __str__(self):
        return f"{self.report_id} - {self.status}"



