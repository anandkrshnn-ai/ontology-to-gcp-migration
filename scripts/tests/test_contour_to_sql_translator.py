import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from contour_to_sql_translator import ContourTranslator

def test_contour_filter_translation():
    payload = {
        "source_dataset": "prj.db.table",
        "steps": [
            {
                "type": "FILTER",
                "config": {
                    "column": "status",
                    "operator": "EQUALS",
                    "value": "ACTIVE"
                }
            }
        ]
    }
    translator = ContourTranslator(payload)
    sql = translator.generate_sql()
    assert "status = 'ACTIVE'" in sql
    assert "WITH" in sql
    assert "step_1_filter AS" in sql

def test_contour_aggregate_translation():
    payload = {
        "source_dataset": "prj.db.table",
        "steps": [
            {
                "type": "AGGREGATE",
                "config": {
                    "group_by": ["category"],
                    "aggregations": [
                        {
                            "column": "amount",
                            "function": "SUM",
                            "alias": "total_amount"
                        }
                    ]
                }
            }
        ]
    }
    translator = ContourTranslator(payload)
    sql = translator.generate_sql()
    assert "SUM(amount) AS total_amount" in sql
    assert "GROUP BY category" in sql
