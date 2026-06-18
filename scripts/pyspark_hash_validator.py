#!/usr/bin/env python3
"""
PySpark Semantic Hash Validator
-------------------------------
This script runs on Google Cloud Dataproc. It calculates a cryptographic hash 
of a migrated BigQuery dataset and compares it against the pre-calculated hash 
of the source Palantir dataset.

If the hashes do not match, it raises a SemanticFidelityError and halts the CI/CD pipeline,
preventing corrupted or semantically altered data from reaching production.
"""

import argparse
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, concat_ws, md5

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SemanticFidelityError(Exception):
    """Exception raised when dataset hashes do not match."""
    pass

def compute_dataset_hash(spark: SparkSession, table_id: str, order_by_col: str) -> str:
    """
    Computes a deterministic hash for an entire dataset.
    Reads from BigQuery, orders by a primary key, concatenates all columns, 
    and returns a single MD5 hash representing the entire dataset state.
    """
    logging.info(f"Reading dataset {table_id} from BigQuery...")
    
    # Load data from BigQuery
    df = spark.read.format("bigquery").option("table", table_id).load()
    
    # Ensure deterministic ordering
    df_sorted = df.orderBy(col(order_by_col))
    
    # Get all column names
    columns = df_sorted.columns
    
    # Concatenate all column values into a single string per row, then hash the row
    df_hashed = df_sorted.withColumn("row_hash", md5(concat_ws("||", *[col(c).cast("string") for c in columns])))
    
    # Collect all row hashes and compute a final composite hash for the dataset
    logging.info("Computing composite semantic hash...")
    row_hashes = [row['row_hash'] for row in df_hashed.select("row_hash").collect()]
    
    # Create a single string of all sorted row hashes and hash that
    composite_string = "".join(row_hashes)
    
    # In a real PySpark distributed environment, you'd use RDD aggregate to avoid driver OOM,
    # but for validation of specific data shards/partitions, this illustrates the pattern.
    import hashlib
    final_hash = hashlib.md5(composite_string.encode('utf-8')).hexdigest()
    
    logging.info(f"Computed Hash for {table_id}: {final_hash}")
    return final_hash

def main():
    parser = argparse.ArgumentParser(description="PySpark Semantic Hash Validator")
    parser.add_argument("--bq_table", required=True, help="BigQuery table ID (e.g., project.dataset.table)")
    parser.add_argument("--primary_key", required=True, help="Column to sort by for deterministic hashing")
    parser.add_argument("--expected_hash", required=True, help="The MD5 hash provided by Palantir prior to migration")
    
    args = parser.parse_args()

    # Initialize Spark Session configured for BigQuery
    spark = SparkSession.builder \
        .appName("SemanticHashValidator") \
        .getOrCreate()

    try:
        actual_hash = compute_dataset_hash(spark, args.bq_table, args.primary_key)
        
        if actual_hash != args.expected_hash:
            error_msg = f"SEMANTIC MISMATCH: Expected {args.expected_hash}, got {actual_hash}. The migrated data is corrupted."
            logging.error(error_msg)
            raise SemanticFidelityError(error_msg)
            
        logging.info(f"SUCCESS: Semantic fidelity verified. Hash {actual_hash} matches Palantir source.")
        
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
