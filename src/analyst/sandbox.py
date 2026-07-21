"""Sandboxed execution for analyst-generated pandas code."""
from __future__ import annotations

import ast
import logging
import textwrap
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_SAFE_MODULES = {"pandas", "numpy", "plotly.express", "matplotlib"}
_BANNED_CALLS = {
    "os", "sys", "subprocess", "socket", "requests", "urllib", "http", "ftp",
    "shutil", "pathlib", "importlib", "builtins", "compile", "exec", "eval",
    "globals", "locals", "__import__", "open", "input", "breakpoint",
}


def _is_safe_node(node: ast.AST) -> bool:
    if isinstance(node, ast.Expression):
        return _is_safe_node(node.body)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return all(_is_safe_node(n) for n in node.body)
    if isinstance(node, ast.If):
        return all(_is_safe_node(n) for n in node.body) and all(
            _is_safe_node(n) for n in node.orelse
        )
    if isinstance(node, ast.For):
        return all(_is_safe_node(n) for n in node.body) and _is_safe_node(node.iter)
    if isinstance(node, ast.While):
        return all(_is_safe_node(n) for n in node.body)
    if isinstance(node, ast.With):
        return all(_is_safe_node(n) for n in node.body)
    if isinstance(node, ast.Try):
        return all(
            _is_safe_node(n)
            for n in node.body + node.handlers + node.orelse + node.finalbody
        )
    if isinstance(node, ast.Return):
        return _is_safe_node(node.value) if node.value else True
    if isinstance(node, ast.Assign):
        return all(_is_safe_node(v) for v in node.value) if node.value else True
    if isinstance(node, ast.AugAssign):
        return _is_safe_node(node.value)
    if isinstance(node, ast.Expr):
        return _is_safe_node(node.value)
    if isinstance(node, (ast.Num, ast.Str, ast.Constant)):
        return True
    if isinstance(node, ast.Name):
        banned = _BANNED_CALLS.intersection({node.id})
        return not banned
    if isinstance(node, ast.Attribute):
        banned = _BANNED_CALLS.intersection({node.attr})
        return not banned
    if isinstance(node, ast.Call):
        return all(_is_safe_node(a) for a in node.args) and _is_safe_node(node.func)
    if isinstance(node, ast.List):
        return all(_is_safe_node(e) for e in node.elts)
    if isinstance(node, ast.Tuple):
        return all(_is_safe_node(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_safe_node(k) for k in node.keys) and all(
            _is_safe_node(v) for v in node.values
        )
    if isinstance(node, ast.BinOp):
        return _is_safe_node(node.left) and _is_safe_node(node.right)
    if isinstance(node, ast.Compare):
        return all(_is_safe_node(c) for c in node.comparators) and _is_safe_node(
            node.left
        )
    if isinstance(node, ast.Subscript):
        return _is_safe_node(node.value) and _is_safe_node(node.slice)
    if isinstance(node, ast.Index):
        return _is_safe_node(node.value)
    if isinstance(node, ast.Slice):
        return all(
            _is_safe_node(n) for n in [node.lower, node.upper, node.step] if n is not None
        )
    if isinstance(node, ast.BoolOp):
        return all(_is_safe_node(v) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        return _is_safe_node(node.operand)
    if isinstance(node, ast.IfExp):
        return (
            _is_safe_node(node.test)
            and _is_safe_node(node.body)
            and _is_safe_node(node.orelse)
        )
    if isinstance(node, ast.JoinedStr):
        return all(_is_safe_node(v) for v in node.values)
    if isinstance(node, ast.FormattedValue):
        return _is_safe_node(node.value)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        return all(
            _is_safe_node(n)
            for n in node.generators
            + (
                [node.elt]
                if hasattr(node, "elt")
                else ([node.key, node.value] if hasattr(node, "key") else [])
            )
        )
    if isinstance(node, ast.comprehension):
        return _is_safe_node(node.target) and _is_safe_node(node.iter) and all(
            _is_safe_node(c) for c in node.ifs
        )
    if isinstance(node, ast.Tuple):
        return all(_is_safe_node(e) for e in node.elts)
    if isinstance(node, ast.Starred):
        return _is_safe_node(node.value)
    return True


def _check_imports(node: ast.AST) -> None:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Import):
            for alias in sub.names:
                top = alias.name.split(".")[0]
                if top not in _SAFE_MODULES:
                    raise ValueError(f"import of {alias.name} is not allowed")
        elif isinstance(sub, ast.ImportFrom):
            top = (sub.module or "").split(".")[0]
            if top not in _SAFE_MODULES:
                raise ValueError(f"from {sub.module} import ... is not allowed")


@dataclass
class SandboxResult:
    ok: bool
    dataframe: list[dict[str, Any]] | None = None
    columns: list[str] | None = None
    chart_spec: dict[str, Any] | None = None
    text: str | None = None
    error: str | None = None


def _has_banned_call(source: str) -> bool:
    lowered = source.lower()
    return any(b in lowered for b in _BANNED_CALLS)


def run_sandbox(
    source: str,
    dataframes: dict[str, pd.DataFrame],
    timeout_seconds: int = 10,
) -> SandboxResult:
    if _has_banned_call(source):
        return SandboxResult(ok=False, error="blocked: banned call in generated code")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return SandboxResult(ok=False, error=f"syntax error: {exc}")
    if not _is_safe_node(tree):
        return SandboxResult(ok=False, error="blocked: unsafe AST node detected")
    _check_imports(tree)
    namespace: dict[str, Any] = {
        "__builtins__": {},
        "pd": __import__("pandas"),
        "np": __import__("numpy"),
        "pl": __import__("plotly.express"),
        "plt": __import__("matplotlib.pyplot"),
    }
    for name, df in dataframes.items():
        namespace[name] = df
    try:
        compiled = compile(tree, "<analyst>", "exec")
        exec(compiled, namespace, namespace)
    except Exception as exc:  # noqa: BLE001
        return SandboxResult(ok=False, error=f"execution error: {exc}")
    result = namespace.get("result")
    fig = namespace.get("fig")
    if result is None:
        return SandboxResult(ok=False, error="no `result` variable produced by the code")
    if isinstance(result, pd.DataFrame):
        df = result
        if len(df) > 1_000:
            df = df.head(1_000)
            text = f"truncated to first 1 000 of {len(result)} rows"
        else:
            text = f"{len(df)} rows"
        return SandboxResult(
            ok=True,
            dataframe=df.to_dict(orient="records"),
            columns=list(df.columns),
            chart_spec=fig.to_dict() if fig is not None else None,
            text=text,
        )
    if isinstance(result, pd.Series):
        df = result.rename("value").reset_index()
        return SandboxResult(
            ok=True,
            dataframe=df.to_dict(orient="records"),
            columns=list(df.columns),
            chart_spec=fig.to_dict() if fig is not None else None,
            text=f"{len(df)} rows",
        )
    return SandboxResult(
        ok=True,
        text=str(result),
        dataframe=None,
        columns=None,
        chart_spec=fig.to_dict() if fig is not None else None,
    )
