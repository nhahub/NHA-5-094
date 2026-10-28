"""
Deterministic Rule & Calculation Engine.
Provides safe, zero-eval AST evaluation of logical and mathematical expressions,
tolerances, dates, string matches, and aggregations against case facts.
"""
from __future__ import annotations
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, Union


class EngineEvaluationError(Exception):
    """Raised when an expression cannot be evaluated due to invalid types or missing context."""
    pass


def resolve_path(context: Dict[str, Any], path: str) -> Any:
    """
    Resolve a dot-notated or colon-notated path in context.
    Supports 'documents.invoice.total', 'case_data.amount', or direct keys.
    """
    if not path or not isinstance(path, str):
        return None
    
    # Direct match first
    if path in context:
        return context[path]
    
    # Split by dot or colon
    parts = re.split(r"[\.:]", path)
    current: Any = context
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return None
        elif isinstance(current, (list, tuple)):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            except ValueError:
                return None
        else:
            return None
    return current


def to_decimal(val: Any) -> Optional[Decimal]:
    """Safely convert numerical input (str, int, float) to Decimal for exact arithmetic."""
    if val is None or val == "":
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, str):
        # Remove currency symbols or commas
        cleaned = re.sub(r"[^\d\.-]", "", val.strip())
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def to_datetime(val: Any) -> Optional[datetime]:
    """Parse various datetime/date formats into a datetime object."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    if isinstance(val, str):
        val_str = val.strip()
        # ISO formats
        try:
            return datetime.fromisoformat(val_str.replace("Z", "+00:00"))
        except ValueError:
            pass
        # Common standard date formats
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
    return None


class RuleEngine:
    """Generic, deterministic rule evaluator."""

    @classmethod
    def evaluate_expression(
        cls, expression: Dict[str, Any], context: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate a declarative JSON rule expression.
        Returns (passed: bool, trace: dict).
        """
        if not expression or not isinstance(expression, dict):
            return False, {"error": "Empty or invalid expression format"}

        operator = expression.get("operator", "EQUAL").upper()
        
        # 1. Resolving operands
        left_spec = expression.get("left")
        right_spec = expression.get("right")

        # Support shorthand 'left_field', 'right_field', 'expected_value'
        if left_spec is None and "left_field" in expression:
            left_spec = {"type": "FIELD", "path": expression["left_field"]}
        if right_spec is None:
            if "right_field" in expression:
                right_spec = {"type": "FIELD", "path": expression["right_field"]}
            elif "expected_value" in expression:
                right_spec = {"type": "LITERAL", "value": expression["expected_value"]}

        left_val = cls._resolve_operand(left_spec, context) if left_spec is not None else None
        right_val = cls._resolve_operand(right_spec, context) if right_spec is not None else None

        # Missing values are policy-controlled so callers can distinguish a
        # genuine mismatch from an incomplete input set.
        missing_policy = str(expression.get("missing_policy", "skip")).lower()
        missing_ops = []
        if left_spec is not None and left_val is None:
            missing_ops.append("left")
        if right_spec is not None and right_val is None:
            missing_ops.append("right")
        null_aware = operator in (
            "EXISTS", "IS_NOT_NULL", "REQUIRED", "IS_EMPTY", "IS_NULL",
        )
        if missing_ops and not null_aware:
            if missing_policy == "raise":
                return False, {
                    "operator": operator,
                    "error": f"Missing {', '.join(missing_ops)} operand",
                    "missing_policy": missing_policy,
                }
            if missing_policy == "default_zero":
                if "left" in missing_ops:
                    left_val = Decimal("0")
                if "right" in missing_ops:
                    right_val = Decimal("0")
            elif missing_policy == "skip":
                return False, {
                    "operator": operator,
                    "skipped": True,
                    "error": f"Missing {', '.join(missing_ops)} operand",
                    "missing_policy": missing_policy,
                }
            else:
                return False, {
                    "operator": operator,
                    "error": f"Unsupported missing_policy: '{missing_policy}'",
                }

        trace: Dict[str, Any] = {
            "operator": operator,
            "left_value": left_val,
            "right_value": right_val,
        }

        # 2. Operator Dispatch
        if operator in ("EQUAL", "EQUALS", "==", "EQ"):
            passed = cls._op_equal(left_val, right_val)

        elif operator in ("NOT_EQUAL", "!=", "NEQ"):
            passed = not cls._op_equal(left_val, right_val)

        elif operator in ("GREATER_THAN", ">", "GT"):
            passed = cls._op_compare(left_val, right_val, lambda a, b: a > b)

        elif operator in ("GREATER_THAN_OR_EQUAL", ">=", "GTE"):
            passed = cls._op_compare(left_val, right_val, lambda a, b: a >= b)

        elif operator in ("LESS_THAN", "<", "LT"):
            passed = cls._op_compare(left_val, right_val, lambda a, b: a < b)

        elif operator in ("LESS_THAN_OR_EQUAL", "<=", "LTE"):
            passed = cls._op_compare(left_val, right_val, lambda a, b: a <= b)

        elif operator in ("EXISTS", "IS_NOT_NULL", "REQUIRED"):
            passed = left_val is not None and left_val != ""
            trace["right_value"] = "<NOT_NULL>"

        elif operator in ("IS_EMPTY", "IS_NULL"):
            passed = left_val is None or left_val == "" or (isinstance(left_val, (list, dict)) and len(left_val) == 0)

        elif operator in ("IN", "CONTAINED_IN"):
            passed = cls._op_in(left_val, right_val)

        elif operator in ("CONTAINS", "INCLUDES"):
            passed = cls._op_in(right_val, left_val)

        elif operator in ("STARTS_WITH",):
            passed = str(left_val or "").startswith(str(right_val or ""))

        elif operator in ("ENDS_WITH",):
            passed = str(left_val or "").endswith(str(right_val or ""))

        elif operator in ("REGEX_MATCH", "REGEX"):
            passed = cls._op_regex(str(left_val or ""), str(right_val or ""))

        elif operator in ("WITHIN_TOLERANCE", "TOLERANCE"):
            tolerance = expression.get("tolerance", 0.0)
            tol_type = expression.get("tolerance_type", "ABSOLUTE").upper()
            passed, delta = cls._op_tolerance(left_val, right_val, tolerance, tol_type)
            trace["tolerance"] = tolerance
            trace["tolerance_type"] = tol_type
            trace["actual_delta"] = str(delta) if delta is not None else None

        elif operator in ("DATE_DIFF_DAYS_LTE", "DATE_WITHIN_DAYS"):
            max_days = expression.get("max_days", right_val or 0)
            passed, days_diff = cls._op_date_diff(left_val, right_val, max_days)
            trace["days_diff"] = days_diff
            trace["max_days"] = max_days

        elif operator == "BETWEEN":
            low = to_decimal(expression.get("between_low", right_val))
            high = to_decimal(expression.get("between_high"))
            actual = to_decimal(left_val)
            passed = actual is not None and low is not None and high is not None and low <= actual <= high
            trace["between_low"] = str(low) if low is not None else None
            trace["between_high"] = str(high) if high is not None else None

        elif operator in ("AND", "ALL"):
            sub_exprs = expression.get("conditions", [])
            sub_results = [cls.evaluate_expression(sub, context) for sub in sub_exprs]
            passed = all(r[0] for r in sub_results)
            trace["sub_traces"] = [r[1] for r in sub_results]

        elif operator in ("OR", "ANY"):
            sub_exprs = expression.get("conditions", [])
            sub_results = [cls.evaluate_expression(sub, context) for sub in sub_exprs]
            passed = any(r[0] for r in sub_results)
            trace["sub_traces"] = [r[1] for r in sub_results]

        elif operator in ("NOT",):
            sub_expr = expression.get("condition", {})
            sub_passed, sub_trace = cls.evaluate_expression(sub_expr, context)
            passed = not sub_passed
            trace["sub_trace"] = sub_trace

        else:
            passed = False
            trace["error"] = f"Unsupported operator: '{operator}'"

        trace["passed"] = passed
        return passed, trace

    @classmethod
    def _resolve_operand(cls, spec: Any, context: Dict[str, Any]) -> Any:
        if spec is None:
            return None
        if not isinstance(spec, dict):
            # Direct literal value
            return spec

        spec_type = spec.get("type", "").upper()

        if spec_type in ("FIELD", "PATH"):
            return resolve_path(context, spec.get("path", ""))

        elif spec_type == "LITERAL":
            return spec.get("value")

        elif spec_type == "CALCULATION":
            # Nested calculation
            return CalculationEngine.evaluate(spec.get("formula", spec), context)

        elif spec_type == "AGGREGATE":
            target_list = resolve_path(context, spec.get("path", ""))
            agg_op = spec.get("aggregate_op", "SUM").upper()
            sub_field = spec.get("item_field")
            return cls._calculate_aggregate(target_list, agg_op, sub_field)

        # If it's a raw dictionary with an operator, evaluate as nested calculation
        if "operator" in spec:
            return CalculationEngine.evaluate(spec, context)

        return spec

    @staticmethod
    def _calculate_aggregate(target_list: Any, agg_op: str, sub_field: Optional[str] = None) -> Any:
        if not isinstance(target_list, (list, tuple)) or not target_list:
            return Decimal("0") if agg_op in ("SUM", "COUNT", "AVG") else None

        values: List[Decimal] = []
        for item in target_list:
            if isinstance(item, dict) and sub_field:
                v = to_decimal(item.get(sub_field))
            else:
                v = to_decimal(item)
            if v is not None:
                values.append(v)

        if not values:
            return Decimal("0")

        if agg_op == "SUM":
            return sum(values)
        elif agg_op == "COUNT":
            return Decimal(len(values))
        elif agg_op == "AVG":
            return sum(values) / Decimal(len(values))
        elif agg_op == "MIN":
            return min(values)
        elif agg_op == "MAX":
            return max(values)
        return None

    @staticmethod
    def _op_equal(left: Any, right: Any) -> bool:
        # Check decimal equality for numbers
        d_left, d_right = to_decimal(left), to_decimal(right)
        if d_left is not None and d_right is not None:
            return d_left == d_right

        # Date equality
        dt_left, dt_right = to_datetime(left), to_datetime(right)
        if dt_left is not None and dt_right is not None:
            return dt_left == dt_right

        # Case-insensitive string equality fallback if strings
        if isinstance(left, str) and isinstance(right, str):
            return left.strip().lower() == right.strip().lower()

        return left == right

    @staticmethod
    def _op_compare(left: Any, right: Any, comparator) -> bool:
        # 1. Decimal numerical comparison
        d_left, d_right = to_decimal(left), to_decimal(right)
        if d_left is not None and d_right is not None:
            return comparator(d_left, d_right)

        # 2. Datetime comparison
        dt_left, dt_right = to_datetime(left), to_datetime(right)
        if dt_left is not None and dt_right is not None:
            return comparator(dt_left, dt_right)

        # 3. String comparison
        if left is not None and right is not None:
            return comparator(str(left), str(right))

        return False

    @staticmethod
    def _op_in(item: Any, collection: Any) -> bool:
        if collection is None:
            return False
        if isinstance(collection, (list, tuple, set)):
            return any(RuleEngine._op_equal(item, elem) for elem in collection)
        if isinstance(collection, str):
            return str(item).lower() in collection.lower()
        return False

    @staticmethod
    def _op_regex(text: str, pattern: str) -> bool:
        try:
            return bool(re.search(pattern, text))
        except re.error:
            return False

    @staticmethod
    def _op_tolerance(
        left: Any, right: Any, tolerance: Union[float, int, str, Decimal], tol_type: str
    ) -> Tuple[bool, Optional[Decimal]]:
        d_left = to_decimal(left)
        d_right = to_decimal(right)
        d_tol = to_decimal(tolerance) or Decimal("0")

        if d_left is None or d_right is None:
            return False, None

        delta = abs(d_left - d_right)
        if tol_type == "PERCENTAGE":
            if d_right == Decimal("0"):
                return delta == Decimal("0"), delta
            pct_diff = (delta / abs(d_right)) * Decimal("100")
            return pct_diff <= d_tol, delta
        else:
            # ABSOLUTE
            return delta <= d_tol, delta

    @staticmethod
    def _op_date_diff(date1: Any, date2: Any, max_days: Any) -> Tuple[bool, Optional[int]]:
        dt1 = to_datetime(date1)
        dt2 = to_datetime(date2)
        d_max = to_decimal(max_days)

        if dt1 is None or dt2 is None or d_max is None:
            return False, None

        diff_days = abs((dt1 - dt2).days)
        return diff_days <= int(d_max), diff_days


class CalculationEngine:
    """Deterministic mathematical and formula calculation engine."""

    @classmethod
    def evaluate(cls, spec: Union[Dict[str, Any], str], context: Dict[str, Any]) -> Any:
        """
        Evaluate a formula specification against context.
        Supports structured JSON AST or infix strings like 'qty * unit_price + tax'.
        """
        if isinstance(spec, str):
            return cls._evaluate_infix_string(spec, context)
        
        if not isinstance(spec, dict):
            return spec

        operator = spec.get("operator", "ADD").upper()

        if operator in ("ADD", "+"):
            operands = cls._get_operands(spec, context)
            decimals = [to_decimal(v) or Decimal("0") for v in operands]
            return sum(decimals)

        elif operator in ("SUBTRACT", "-"):
            operands = cls._get_operands(spec, context)
            if not operands:
                return Decimal("0")
            res = to_decimal(operands[0]) or Decimal("0")
            for op_val in operands[1:]:
                res -= to_decimal(op_val) or Decimal("0")
            return res

        elif operator in ("MULTIPLY", "*"):
            operands = cls._get_operands(spec, context)
            if not operands:
                return Decimal("0")
            res = Decimal("1")
            for op_val in operands:
                val = to_decimal(op_val)
                if val is None:
                    return None
                res *= val
            return res

        elif operator in ("DIVIDE", "/"):
            left = to_decimal(RuleEngine._resolve_operand(spec.get("left", spec.get("numerator")), context))
            right = to_decimal(RuleEngine._resolve_operand(spec.get("right", spec.get("denominator")), context))
            if left is None or right is None or right == Decimal("0"):
                return None
            return left / right

        elif operator in ("ROUND",):
            val = to_decimal(RuleEngine._resolve_operand(spec.get("value", spec.get("left")), context))
            precision = int(spec.get("precision", 2))
            if val is None:
                return None
            return round(val, precision)

        elif operator in ("ABS",):
            val = to_decimal(RuleEngine._resolve_operand(spec.get("value", spec.get("left")), context))
            return abs(val) if val is not None else None

        elif operator in ("MIN",):
            operands = [to_decimal(v) for v in cls._get_operands(spec, context)]
            valid = [v for v in operands if v is not None]
            return min(valid) if valid else None

        elif operator in ("MAX",):
            operands = [to_decimal(v) for v in cls._get_operands(spec, context)]
            valid = [v for v in operands if v is not None]
            return max(valid) if valid else None

        elif operator in ("IF_ELSE", "IF"):
            condition = spec.get("condition", {})
            cond_passed, _ = RuleEngine.evaluate_expression(condition, context)
            if cond_passed:
                return RuleEngine._resolve_operand(spec.get("then"), context)
            else:
                return RuleEngine._resolve_operand(spec.get("else"), context)

        return None

    @classmethod
    def _get_operands(cls, spec: Dict[str, Any], context: Dict[str, Any]) -> List[Any]:
        if "operands" in spec:
            return [RuleEngine._resolve_operand(item, context) for item in spec["operands"]]
        
        results: List[Any] = []
        if "left" in spec:
            results.append(RuleEngine._resolve_operand(spec["left"], context))
        if "right" in spec:
            results.append(RuleEngine._resolve_operand(spec["right"], context))
        return results

    @classmethod
    def _evaluate_infix_string(cls, formula_str: str, context: Dict[str, Any]) -> Optional[Decimal]:
        """
        Safely tokenize and evaluate simple arithmetic infix formulas like 'a * b + c - d'.
        No eval() is used; parses identifiers and resolves them from context.
        """
        # Tokenize identifiers, numbers, and operators (+, -, *, /, (, ))
        tokens = re.findall(r"[a-zA-Z0-9_\.:]+|[+\-*/()]|\d+(?:\.\d+)?", formula_str)
        if not tokens:
            return None

        # Replace identifiers with numerical literals from context
        resolved_tokens: List[str] = []
        for t in tokens:
            if t in ("+", "-", "*", "/", "(", ")"):
                resolved_tokens.append(t)
            elif re.match(r"^\d+(?:\.\d+)?$", t):
                resolved_tokens.append(t)
            else:
                val = resolve_path(context, t)
                d_val = to_decimal(val)
                if d_val is None:
                    # Missing operand in calculation
                    return None
                resolved_tokens.append(str(d_val))

        # Safe recursive-descent parser for arithmetic without eval
        try:
            return cls._parse_arithmetic_tokens(resolved_tokens)
        except Exception:
            return None

    @classmethod
    def _parse_arithmetic_tokens(cls, tokens: List[str]) -> Decimal:
        """Standard shunting-yard algorithm to evaluate arithmetic tokens."""
        precedence = {"+": 1, "-": 1, "*": 2, "/": 2}
        output_queue: List[Union[Decimal, str]] = []
        op_stack: List[str] = []

        for token in tokens:
            if re.match(r"^-?\d+(?:\.\d+)?$", token):
                output_queue.append(Decimal(token))
            elif token in precedence:
                while (op_stack and op_stack[-1] in precedence and
                       precedence[op_stack[-1]] >= precedence[token]):
                    output_queue.append(op_stack.pop())
                op_stack.append(token)
            elif token == "(":
                op_stack.append(token)
            elif token == ")":
                while op_stack and op_stack[-1] != "(":
                    output_queue.append(op_stack.pop())
                if op_stack and op_stack[-1] == "(":
                    op_stack.pop()

        while op_stack:
            output_queue.append(op_stack.pop())

        # Evaluate RPN queue
        eval_stack: List[Decimal] = []
        for item in output_queue:
            if isinstance(item, Decimal):
                eval_stack.append(item)
            elif isinstance(item, str) and item in precedence:
                if len(eval_stack) < 2:
                    raise EngineEvaluationError("Malformed arithmetic expression")
                b = eval_stack.pop()
                a = eval_stack.pop()
                if item == "+":
                    eval_stack.append(a + b)
                elif item == "-":
                    eval_stack.append(a - b)
                elif item == "*":
                    eval_stack.append(a * b)
                elif item == "/":
                    if b == Decimal("0"):
                        raise EngineEvaluationError("Division by zero")
                    eval_stack.append(a / b)

        if len(eval_stack) != 1:
            raise EngineEvaluationError("Malformed evaluation stack")
        return eval_stack[0]
