# myapp/tasks.py
import csv
from datetime import datetime, timedelta
from pytz import timezone, utc
from django.utils import timezone as django_timezone
from .models import StoreData, StoreActivity, BusinessHours, Report
from io import StringIO
from django.core.files.base import ContentFile
import pandas as pd
from StoreMonitoring.celery import app
from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)


@app.task(bind=True)
def import_csv_every_hour():
    # Read Timezone data
    logger.info('data import task received!')
    with open(r'store\data_file\timezone_data.csv', 'r') as file:
        logger.info('import timezone data start')
        reader = csv.DictReader(file)
        for row in reader:
            store_id = row['store_id']
            timezone_str = row['timezone_str']
            store, _ = StoreData.objects.get_or_create(store_id=store_id)
            store.timezone_str = timezone_str
            store.save()

    # Read and import Business hours data
    with open(r'store\data_file\business_hours_data.csv', 'r') as file:
        logger.info('import business hours data start')
        reader = csv.DictReader(file)
        for row in reader:
            store_id = row['store_id']
            day_of_week = int(row['day'])  # Convert day to integer
            start_time_local = row['start_time_local']
            end_time_local = row['end_time_local']
            store = StoreData.objects.filter(store_id=store_id).last()
            if store:
                if start_time_local and end_time_local:
                    BusinessHours.objects.create(
                        store=store,
                        day_of_week=day_of_week,
                        start_time_local=start_time_local,
                        end_time_local=end_time_local
                    )
                else:
                    # If data is missing, assume the store is open 24/7
                    BusinessHours.objects.create(
                        store=store,
                        day_of_week=day_of_week,
                        start_time_local='00:00:00',
                        end_time_local='23:59:59'
                    )

    # Read and import Store activity data
    with open(r'store\data_file\store_activity_data.csv', 'r') as file:
        logger.info('import store activity data start')
        reader = csv.DictReader(file)
        for row in reader:
            store_id = row['store_id']
            status = row['status']
            timestamp_utc = row['timestamp_utc']
            store = StoreData.objects.filter(store_id=store_id).last()
            # Convert UTC timestamp to datetime object
            if store:
                timestamp_utc = datetime.strptime(timestamp_utc, '%Y-%m-%d %H:%M:%S.%f UTC')
                # take store timezone string
                store_timezone = timezone(store.timezone_str)
                # Convert UTC timestamp to the store's local timezone
                timestamp_local = django_timezone.make_aware(timestamp_utc, store_timezone)
                # pre save local data
                StoreActivity.objects.create(
                    store=store,
                    status=status,
                    timestamp_utc=timestamp_utc,
                    timestamp_local=timestamp_local
                )

    logger.info('data inserted successfully!')        

# task to generate report
@app.task(bind=True)
def generate_report(self, report_id):
    logger.info(f'generate_report task received!')
    # Fetch all stores
    stores = StoreData.objects.all()
    # Prepare a list to collect report data
    report_data = []
    # hard code current time stamp from UTC
    current_timestamp = datetime.utcnow()
    # run for all stores
    for store in stores:
        # Define time ranges for report calculations: last hour, last day, last week
        time_ranges = {
            'last_hour': (current_timestamp - timedelta(hours=1), current_timestamp),
            'last_day': (current_timestamp - timedelta(days=1), current_timestamp),
            'last_week': (current_timestamp - timedelta(days=7), current_timestamp),
        }

        # Initialize report row for this store
        store_report = {
            'store_id': store.store_id,
            'uptime_last_hour': 0,
            'uptime_last_day': 0,
            'uptime_last_week': 0,
            'downtime_last_hour': 0,
            'downtime_last_day': 0,
            'downtime_last_week': 0,
        }

        for period_key, (start, end) in time_ranges.items():
            # Fetch business hours applicable within the time range
            if period_key == 'last_week': # we have applicable business hours for max 7 days
                applicable_business_hours = BusinessHours.objects.filter(
                    store=store
                )
            elif period_key == 'last_day': # last day as start week day
                applicable_business_hours = BusinessHours.objects.filter(
                    store=store,
                    day_of_week=start.weekday()
                )   
            else:
                applicable_business_hours = BusinessHours.objects.filter(
                    store=store,
                    day_of_week=end.weekday()
                ) 

            # Aggregate activity data within the time range
            activities = StoreActivity.objects.filter(
                store=store,
                timestamp_local__gte=start, 
                timestamp_local__lt=end
            ).order_by('timestamp_local')


            # Initialize counters for uptime and downtime
            total_uptime = timedelta(0)
            total_downtime = timedelta(0)

            # Process each set of business hours
            for bh in applicable_business_hours:
                # business hour stard/end date time
                bh_start = pd.Timestamp(f'{start.date()} {bh.start_time_local}').to_pydatetime()
                bh_end = pd.Timestamp(f'{start.date()} {bh.end_time_local}').to_pydatetime()

                # Calculate the overlap of business hours with the current time range
                bh_start = max(bh_start, start)
                bh_end = min(bh_end, end)

                bh_start = bh_start.astimezone(utc) # we need to compare datetime awair
                bh_end = bh_end.astimezone(utc)
                last_status = 'inactive'  # Default assumption
                last_time = bh_start

                # Calculate uptime/downtime within this business period
                for activity in activities:
                    activity_time = activity.timestamp_local
                    if activity_time < bh_start:
                        continue

                    if activity_time > bh_end:
                        break

                    # Calculate duration from last_time to the current activity time within business hours
                    if last_time < activity_time:
                        duration = min(activity_time, bh_end) - last_time
                        if last_status == 'active':
                            total_uptime += duration
                        else:
                            total_downtime += duration
                    # every time update veriable as last activity data
                    last_status = activity.status
                    last_time = activity_time

                # Account for any remaining time after the last activity to business hours end
                if last_time < bh_end:
                    duration = bh_end - last_time
                    if last_status == 'active':
                        total_uptime += duration
                    else:
                        total_downtime += duration

            # Store the computed uptime and downtime (convert to minutes for hours and hours for days/weeks)
            store_report[f'uptime_{period_key}'] = round((total_uptime.total_seconds() / 60), 2) if 'hour' in period_key else round((total_uptime.total_seconds() / 3600), 2)
            store_report[f'downtime_{period_key}'] = round((total_downtime.total_seconds() / 60), 2) if 'hour' in period_key else round((total_downtime.total_seconds() / 3600), 2)

        # Append the calculated store report to the main report data list
        report_data.append(store_report)

    # Create a DataFrame from the collected data and save it as a CSV
    df = pd.DataFrame(report_data)
    # get the report object
    report = Report.objects.get(report_id=report_id)

    # Assuming 'df' is the DataFrame containing the data
    # Convert DataFrame to CSV string
    csv_string = df.to_csv(index=False)
    # Create a temporary file in memory
    temp_file = StringIO()
    # Write the CSV string into the temporary file
    temp_file.write(csv_string)
    # Save the DataFrame to the FileField
    report.file.save('data.csv', ContentFile(temp_file.getvalue()))
    report.status = 'Complete' # make task as complete
    report.save()
    logger.info("Task Completed")
    # Close the temporary file
    temp_file.close()


