import datetime
from google.cloud import bigquery

# EDIT THESE:
BILLING_PROJECT_ID = "migiration-demo"        # project with the billing export
BILLING_DATASET = "billing_export"           # dataset name
BILLING_TABLE = "gcp_billing_export"         # table name

def main():
    client = bigquery.Client(project=BILLING_PROJECT_ID)

    # Today's date in UTC
    today = datetime.date.today().isoformat()

    query = f"""
    SELECT
      DATE(usage_start_time) AS usage_date,
      SUM(cost) AS total_cost
    FROM `{BILLING_PROJECT_ID}.{BILLING_DATASET}.{BILLING_TABLE}`
    WHERE
      service.description = "Cloud Spanner"
      AND DATE(usage_start_time) = "{today}"
    GROUP BY usage_date
    ORDER BY usage_date
    """

    print("Running query for today's Cloud Spanner cost...")
    print(query)

    job = client.query(query)
    result = list(job.result())

    if not result:
        print(f"No Cloud Spanner cost recorded for {today}.")
        return

    for row in result:
        print(f"Date: {row.usage_date}, Spanner cost today: {row.total_cost:.6f} (in billing currency)")

if __name__ == "__main__":
    main()
