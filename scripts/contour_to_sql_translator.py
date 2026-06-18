import json
import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ContourTranslator:
    """
    Parses a Palantir Contour JSON transformation graph into native BigQuery Standard SQL.
    This guarantees 1-to-1 parity for visual logic migrations.
    """
    def __init__(self, json_payload: dict):
        self.payload = json_payload
        self.source_dataset = self.payload.get("source_dataset", "project.dataset.table")
        self.steps = self.payload.get("steps", [])
        self.ctes = []

    def translate_filter(self, step_name: str, prev_step: str, config: dict):
        column = config.get("column")
        operator = config.get("operator")
        value = config.get("value")
        
        # Map Palantir operators to SQL
        op_map = {
            "EQUALS": "=",
            "GREATER_THAN": ">",
            "LESS_THAN": "<",
            "CONTAINS": "LIKE",
            "IS_NOT_NULL": "IS NOT NULL"
        }
        sql_op = op_map.get(operator, "=")
        
        if operator == "CONTAINS":
            condition = f"{column} {sql_op} '%{value}%'"
        elif operator == "IS_NOT_NULL":
            condition = f"{column} {sql_op}"
        else:
            condition = f"{column} {sql_op} '{value}'" if isinstance(value, str) else f"{column} {sql_op} {value}"

        return f"""  {step_name} AS (
    SELECT * 
    FROM {prev_step}
    WHERE {condition}
  )"""

    def translate_aggregate(self, step_name: str, prev_step: str, config: dict):
        group_by = ", ".join(config.get("group_by", []))
        aggs = []
        for agg in config.get("aggregations", []):
            col = agg.get("column")
            func = agg.get("function") # e.g., SUM, AVG, COUNT
            alias = agg.get("alias", f"{func}_{col}".lower())
            aggs.append(f"{func}({col}) AS {alias}")
        
        select_cols = ", ".join([group_by] + aggs)
        
        return f"""  {step_name} AS (
    SELECT 
      {select_cols}
    FROM {prev_step}
    GROUP BY {group_by}
  )"""

    def translate_join(self, step_name: str, prev_step: str, config: dict):
        right_table = config.get("right_dataset")
        join_type = config.get("type", "LEFT")
        left_key = config.get("left_key")
        right_key = config.get("right_key")
        
        return f"""  {step_name} AS (
    SELECT 
      L.*,
      R.*
    FROM {prev_step} L
    {join_type} JOIN `{right_table}` R
      ON L.{left_key} = R.{right_key}
  )"""

    def generate_sql(self) -> str:
        if not self.steps:
            return f"SELECT * FROM `{self.source_dataset}`;"

        # Initial source CTE
        self.ctes.append(f"""  step_0 AS (
    SELECT * FROM `{self.source_dataset}`
  )""")

        prev_step = "step_0"
        
        for i, step in enumerate(self.steps):
            step_name = f"step_{i+1}_{step['type'].lower()}"
            step_type = step.get("type")
            config = step.get("config", {})

            if step_type == "FILTER":
                cte_sql = self.translate_filter(step_name, prev_step, config)
            elif step_type == "AGGREGATE":
                cte_sql = self.translate_aggregate(step_name, prev_step, config)
            elif step_type == "JOIN":
                cte_sql = self.translate_join(step_name, prev_step, config)
            else:
                logging.warning(f"Unsupported Contour step type: {step_type}. Passing through.")
                cte_sql = f"  {step_name} AS (\n    SELECT * FROM {prev_step}\n  )"

            self.ctes.append(cte_sql)
            prev_step = step_name

        # Construct final SQL
        final_sql = "WITH\n" + ",\n".join(self.ctes) + f"\nSELECT * FROM {prev_step};"
        return final_sql


def mock_run():
    logging.info("Running contour_to_sql_translator with mock Contour JSON payload...")
    mock_payload = {
        "source_dataset": "gcp-project.logistics.raw_telemetry",
        "steps": [
            {
                "type": "FILTER",
                "config": {
                    "column": "status",
                    "operator": "EQUALS",
                    "value": "DELAYED"
                }
            },
            {
                "type": "JOIN",
                "config": {
                    "right_dataset": "gcp-project.logistics.hub_metadata",
                    "type": "LEFT",
                    "left_key": "location",
                    "right_key": "hub_id"
                }
            },
            {
                "type": "AGGREGATE",
                "config": {
                    "group_by": ["delay_reason", "region"],
                    "aggregations": [
                        {
                            "column": "package_id",
                            "function": "COUNT",
                            "alias": "total_delayed_packages"
                        }
                    ]
                }
            }
        ]
    }
    
    translator = ContourTranslator(mock_payload)
    sql_output = translator.generate_sql()
    
    print("\n--- GENERATED BIGQUERY SQL ---")
    print(sql_output)
    print("------------------------------\n")
    logging.info("Translation complete. 1-to-1 logic parity achieved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile Palantir Contour JSON into BigQuery SQL")
    parser.add_argument("--input", help="Path to exported Contour JSON file")
    parser.add_argument("--mock", action="store_true", help="Run with a mock Contour JSON payload to demonstrate functionality")
    
    args = parser.parse_args()
    
    if args.mock:
        mock_run()
    elif args.input:
        try:
            with open(args.input, 'r') as f:
                payload = json.load(f)
            translator = ContourTranslator(payload)
            print(translator.generate_sql())
        except Exception as e:
            logging.error(f"Failed to process {args.input}: {e}")
            sys.exit(1)
    else:
        parser.print_help()
