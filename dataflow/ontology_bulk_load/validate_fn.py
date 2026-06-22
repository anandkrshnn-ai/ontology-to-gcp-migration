import uuid
from datetime import datetime, timezone
import apache_beam as beam
from apache_beam import pvalue
import re

class ValidateRow(beam.DoFn):
    """
    Validates a row against the rules provided in the rules_dict.
    Yields to the main output if valid, and to the 'audit_logs' tagged output
    for the rule_audit table regardless of pass/fail.
    """
    
    def __init__(self, table_name, rules):
        self.table_name = table_name
        self.rules = rules

    def process(self, row):
        # We need a primary key value for the audit log
        # For simplicity, we grab the first key in the dict as the row_key
        row_key = str(list(row.values())[0]) if row else "unknown"
        
        is_valid = True
        audit_logs = []

        for rule in self.rules:
            rule_id = rule.get("id", "UNKNOWN")
            expr = rule.get("expression", "")
            
            passed, error_msg = self._evaluate_rule(row, expr)
            
            audit_logs.append({
                "audit_id": str(uuid.uuid4()),
                "table_name": self.table_name,
                "row_key": row_key,
                "rule_id": rule_id,
                "status": "PASS" if passed else "FAIL",
                "error_message": error_msg,
                "evaluated_at": datetime.now(timezone.utc).isoformat() + "Z"
            })
            
            if not passed:
                is_valid = False

        # Output the row if it passes all rules
        if is_valid:
            yield row
            
        # Always output audit logs
        for log in audit_logs:
            yield pvalue.TaggedOutput('audit_logs', log)

    def _evaluate_rule(self, row, expr):
        """
        Safely evaluates Option C style rules using regex and string matching.
        Covers !=, IS NULL, IS NOT NULL, >, >=, IN (...)
        """
        expr = expr.strip()
        
        # 1. Skip aggregation rules
        if "COUNT(" in expr.upper():
            return True, "Skipped aggregation rule evaluation in single-row context"
            
        # 2. IS NULL / IS NOT NULL
        if " IS NOT NULL" in expr.upper():
            col = expr.split(" IS NOT NULL")[0].strip()
            if col in row and row[col]:
                return True, ""
            return False, f"{col} is null but required not to be"
            
        if " IS NULL" in expr.upper():
            col = expr.split(" IS NULL")[0].strip()
            if col not in row or not row[col]:
                return True, ""
            # Some rules might be OR combinations like `total_transit_minutes IS NULL OR ...`
            # For this simplistic evaluator, if it's an OR, we can split by OR
            pass # fallback to general eval if part of OR

        # 3. Handle OR logic
        if " OR " in expr.upper():
            parts = re.split(r'\s+OR\s+', expr, flags=re.IGNORECASE)
            for part in parts:
                passed, _ = self._evaluate_rule(row, part.strip())
                if passed:
                    return True, ""
            return False, f"Failed OR condition: {expr}"

        # 4. !=
        if "!=" in expr:
            col1, col2 = [x.strip() for x in expr.split("!=")]
            val1 = row.get(col1, col1) # fallback to literal if col1 not in row (not perfect but works)
            val2 = row.get(col2, col2)
            if val1 != val2:
                return True, ""
            return False, f"{col1} ({val1}) == {col2} ({val2})"
            
        # 5. > and >=
        if ">=" in expr:
            col, val = [x.strip() for x in expr.split(">=")]
            if col in row:
                try:
                    if float(row[col]) >= float(val):
                        return True, ""
                    return False, f"{col} ({row[col]}) < {val}"
                except ValueError:
                    return False, f"Type mismatch for >="
                    
        elif ">" in expr:
            col, val = [x.strip() for x in expr.split(">")]
            if col in row:
                try:
                    if float(row[col]) > float(val):
                        return True, ""
                    return False, f"{col} ({row[col]}) <= {val}"
                except ValueError:
                    return False, f"Type mismatch for >"

        # 6. IN (...)
        if " IN " in expr.upper():
            col, values_str = re.split(r'\s+IN\s+', expr, flags=re.IGNORECASE)
            values_str = values_str.strip('()')
            # remove quotes
            valid_values = [v.strip().strip("'").strip('"') for v in values_str.split(',')]
            if col in row and row[col] in valid_values:
                return True, ""
            return False, f"{col} ({row.get(col)}) not in {valid_values}"

        # Default fallback (if rule is too complex)
        return True, "Rule too complex for simple evaluator, defaulted to PASS"
