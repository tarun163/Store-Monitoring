# Store-Monitoring
## Requirements
Python, Django, Postgres, Celery
## Installation
##### Create virtual env
##### install requirements
##### Setup Postgres database
##### Create folder StoreMonitoring/store/data_files
##### upload required files "timezone_data", "store_activity_data", "business_hours_data" in CSV format
## process
##### store/tasks.py -> We have two functions here import_csv_every_hour will be automatically triggered by celery every hour (because files don't have datetime column we have to build logic to erase and update with new data) second is generate_report, which will take the report_id parameter to store generated file into the particular record. 
##### store/views.py -> api/trigger_report post API will trigger asynchronous api/generate_report task with report id, get_report will take report_id as parameter and response the status of the file. one another api/trigger API to test the gererate_report function.
