# edof/utils/safe_eval.py
"""
Safe expression evaluator for `obj.visible_if`.

Supported:
  - Literals: numbers, strings, True/False/None
  - Variable lookup by name (from a context dict)
  - Comparisons: <, <=, ==, !=, >=, >, in, not in
  - Arithmetic: +, -, *, /, //, %, **
  - Boolean: and, or, not
  - Unary: -, +
  - Parentheses

Forbidden:
  - Function calls
  - Attribute access
  - Imports
  - Subscript with non-constant
  - Lambda, comprehensions

Returns the boolean result of the expression, or None on error.
"""
from __future__ import annotations
import ast
import operator
from typing import Optional


class _UnsafeExpression(Exception):
    pass


# v4.4.0 security: visible_if comes straight from the (untrusted) file, so the
# evaluator must be DoS-proof. Guarded operations below: ** is capped (a
# 9**9**9 in a document froze the process before), sequence repetition and
# addition are size-capped.
_MAX_POW_EXP    = 64        # |exponent| cap for **
_MAX_NUM_BITS   = 4096      # cap on integer magnitude for ** results
_MAX_SEQ_LEN    = 10000     # cap on len(str/list/tuple) from * and +


def _safe_pow(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise _UnsafeExpression("** needs numbers")
    if abs(b) > _MAX_POW_EXP:
        raise _UnsafeExpression("** exponent too large")
    if isinstance(a, int) and isinstance(b, int) and b > 0:
        if a != 0 and abs(a).bit_length() * b > _MAX_NUM_BITS:
            raise _UnsafeExpression("** result too large")
    return operator.pow(a, b)


def _safe_mult(a, b):
    for seq, n in ((a, b), (b, a)):
        if isinstance(seq, (str, list, tuple)) and isinstance(n, (int, float)):
            if n * len(seq) > _MAX_SEQ_LEN:
                raise _UnsafeExpression("* repetition too large")
    return operator.mul(a, b)


def _safe_add(a, b):
    if isinstance(a, (str, list, tuple)) and isinstance(b, (str, list, tuple)):
        if len(a) + len(b) > _MAX_SEQ_LEN:
            raise _UnsafeExpression("+ result too large")
    return operator.add(a, b)


_BIN_OPS = {
    ast.Add:     _safe_add,
    ast.Sub:     operator.sub,
    ast.Mult:    _safe_mult,
    ast.Div:     operator.truediv,
    ast.FloorDiv:operator.floordiv,
    ast.Mod:     operator.mod,
    ast.Pow:     _safe_pow,
}

_CMP_OPS = {
    ast.Lt:    operator.lt,  ast.LtE: operator.le,
    ast.Gt:    operator.gt,  ast.GtE: operator.ge,
    ast.Eq:    operator.eq,  ast.NotEq: operator.ne,
    ast.In:    lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not:  operator.not_,
}


def _coerce_number(v):
    """Try to parse strings as numbers for variable comparisons."""
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, str):
        try:
            if "." in v: return float(v)
            return int(v)
        except ValueError:
            return v
    return v


def _eval(node: ast.AST, ctx: dict):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in ctx:
            return _coerce_number(ctx[node.id])
        if node.id == "True":  return True
        if node.id == "False": return False
        if node.id == "None":  return None
        return None    # undefined variable -> None (falsy)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None: raise _UnsafeExpression(f"Unsafe unary: {type(node.op).__name__}")
        return op(_eval(node.operand, ctx))
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None: raise _UnsafeExpression(f"Unsafe binop: {type(node.op).__name__}")
        return op(_eval(node.left, ctx), _eval(node.right, ctx))
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(v, ctx) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_eval(v, ctx) for v in node.values)
        raise _UnsafeExpression(f"Unsafe boolop: {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        for op_node, right_node in zip(node.ops, node.comparators):
            op = _CMP_OPS.get(type(op_node))
            if op is None:
                raise _UnsafeExpression(f"Unsafe compare: {type(op_node).__name__}")
            right = _eval(right_node, ctx)
            try:
                if not op(left, right):
                    return False
            except TypeError:
                # Fall back to string comparison if mixed types
                try:
                    if not op(str(left), str(right)):
                        return False
                except Exception:
                    return False
            left = right
        return True
    if isinstance(node, ast.List):
        return [_eval(e, ctx) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval(e, ctx) for e in node.elts)
    raise _UnsafeExpression(f"Unsafe node: {type(node).__name__}")


def evaluate(expression: str, context: dict) -> Optional[bool]:
    """Evaluate `expression` against `context` (dict of variable name -> value).

    Returns the boolean result, or None if the expression is invalid or unsafe.
    Never raises — errors are silently treated as None (falsy).
    """
    if not expression or not expression.strip():
        return True
    try:
        tree = ast.parse(expression, mode="eval")
        return bool(_eval(tree.body, context))
    except (_UnsafeExpression, SyntaxError, ValueError, TypeError,
            ZeroDivisionError, OverflowError, MemoryError, RecursionError):
        return None


def is_visible(obj, var_store=None) -> bool:
    """Check if an object should be visible. Honors both .visible flag and .visible_if."""
    if not getattr(obj, "visible", True):
        return False
    expr = getattr(obj, "visible_if", "") or ""
    if not expr.strip():
        return True
    ctx = {}
    if var_store is not None:
        for name in var_store.names():
            ctx[name] = var_store.get(name)
    result = evaluate(expr, ctx)
    return bool(result) if result is not None else True
