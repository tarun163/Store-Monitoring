# myapp/views.py
import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from .tasks import generate_report
from django.views.decorators.csrf import csrf_exempt
from .models import Report
from datetime import datetime, timedelta
from pytz import timezone, utc
from .models import StoreData, StoreActivity, BusinessHours, Report
from io import StringIO
from django.core.files.base import ContentFile
import pandas as pd

@csrf_exempt
@require_POST
def trigger_report(request):
    print("trigger_report request")
    report = Report.objects.create()

    # Trigger the report generation task and pass the report ID
    generate_report.delay(report.report_id)

    # Log success message
    print('Report generation triggered successfully.')
    return JsonResponse({'report_id': report.report_id})

@require_GET
def get_report(request):
    print(request.GET)
    report_id = request.GET.get('report_id')
    if report_id:
        # get the report created
        report = Report.objects.filter(report_id=report_id).last()
        if report:
            if report.status == 'Running':
                # Report generation is still in progress
                return JsonResponse({'status': 'Running'})
            else:
                # Report generation is complete, fetch the CSV file
                csv_data = report.file
                if csv_data:
                    # Return the CSV file
                    response = HttpResponse(csv_data, content_type='text/csv')
                    response['Content-Disposition'] = 'attachment; filename="report.csv"'
                    response['status'] = 'Complete'
                    return response
                
        else:
            JsonResponse({'error': 'Invailid report_id'})        
    else:
        return JsonResponse({'error': 'Missing report_id parameter'})
    
@require_GET
def generate_report_one(request):
    report_id = request.GET.get('report_id')
    # Fetch all stores
    stores = StoreData.objects.all()[:200]
    # Prepare a list to collect report data
    report_data = []
    current_timestamp = datetime.utcnow() - timedelta(days=467)
    print("current-time", current_timestamp)
    for store in stores:
        # Define time ranges for report calculations: last hour, last day, last week
        time_ranges = {
            'last_hour': (current_timestamp - timedelta(hours=1), current_timestamp),
            'last_day': (current_timestamp - timedelta(days=1), current_timestamp),
            'last_week': (current_timestamp - timedelta(days=7), current_timestamp),
        }
        # print("time_range", time_ranges)
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
            if period_key == 'last_week':
                applicable_business_hours = BusinessHours.objects.filter(
                    store=store
                )
            elif period_key == 'last_day':
                applicable_business_hours = BusinessHours.objects.filter(
                    store=store,
                    day_of_week=start.weekday()
                )   
            else:
                applicable_business_hours = BusinessHours.objects.filter(
                    store=store,
                    day_of_week=end.weekday()
                ) 

            # print(f"applicable hours for {period_key}", applicable_business_hours)
            # Aggregate activity data within the time range
            activities = StoreActivity.objects.filter(
                store=store,
                timestamp_local__gte=start, 
                timestamp_local__lt=end
            ).order_by('timestamp_local')
            print(activities.count())
            # Initialize counters for uptime and downtime
            total_uptime = timedelta(0)
            total_downtime = timedelta(0)

            # Process each set of business hours
            for bh in applicable_business_hours:
                bh_start = pd.Timestamp(f'{start.date()} {bh.start_time_local}').to_pydatetime()
                bh_end = pd.Timestamp(f'{start.date()} {bh.end_time_local}').to_pydatetime()

                # Calculate the overlap of business hours with the current time range
                
                bh_start = max(bh_start, start)
                bh_end = min(bh_end, end)

                # Calculate uptime/downtime within this business period
                bh_start = bh_start.astimezone(utc)
                bh_end = bh_end.astimezone(utc)
                last_status = 'active'  # Default assumption
                last_time = bh_start

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

                    last_status = activity.status
                    last_time = activity_time

                # Account for any remaining time after the last activity to business hours end
                if activities.count() > 0:
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
    report.status = 'Complete'
    report.save()
    # Close the temporary file
    temp_file.close()

    return JsonResponse({'status': 'Complete'})
    

