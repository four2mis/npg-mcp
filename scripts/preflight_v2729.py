"""Static preflight for the v2.72.9 upstream-sync patch (no network)."""
import ast
import re
import sys

MAIN = "npg_mcp/main.py"
UM = "npg_mcp/upstream_models.py"
DESC_LIMIT = 460

fails = []

# 1. AST parse
for path in (MAIN, UM):
    try:
        ast.parse(open(path, encoding="utf-8").read())
        print(f"AST OK: {path}")
    except SyntaxError as e:
        fails.append(f"AST FAIL {path}: {e}")

src = open(MAIN, encoding="utf-8").read()
tree = ast.parse(src)

tools = {}
for node in ast.walk(tree):
    if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        for d in node.decorator_list:
            if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool":
                kw = {k.arg: k.value for k in d.keywords}
                name = getattr(kw.get("name"), "value", None)
                desc = getattr(kw.get("description"), "value", "")
                if name:
                    tools.setdefault(name, []).append((len(desc), node))

# 2. tool count + duplicates
deco_count = len(re.findall(r'@mcp\.tool\(name="', src))
print(f"decorators: {deco_count}  unique names: {len(tools)}")
dups = sorted(n for n, v in tools.items() if len(v) > 1)
if dups:
    fails.append(f"DUPLICATE tool names: {dups}")
else:
    print("no duplicate tool names")

# 3. DESC_LEN
over = sorted((ln, n) for n, v in tools.items() for ln, _ in v if ln > DESC_LIMIT)
mx = max((ln, n) for n, v in tools.items() for ln, _ in v)
print(f"max description: {mx[0]} chars ({mx[1]})")
if over:
    fails.append(f"DESC_LEN over {DESC_LIMIT}: {over}")

# 4. targeted assertions
def sig(node):
    return [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]

def get(name):
    return tools[name][0][1]

def ann(name, arg):
    a = next((a for a in get(name).args.args if a.arg == arg), None)
    if a is None:
        return ""
    return ast.unparse(a.annotation) if a.annotation else ""

def log_type_ann(name):
    return ann(name, "log_type")


checks = [
    ("npg_list_banned_ips has ban_type", "ban_type" in sig(get("npg_list_banned_ips"))),
    ("ban_type enum has all 7 values",
     all(v in ast.unparse(get("npg_list_banned_ips").args.args[0].annotation)
         for v in ("all", "auto", "manual", "waf", "fail2ban", "rate_limit", "bot"))),
    ("ban_type sends query type", 'params["type"] = str(ban_type)' in src),
    ("npg_get_logs log_type has stream", "stream" in log_type_ann("npg_get_logs")),
    ("npg_get_log_stats log_type has stream",
     "stream" in log_type_ann("npg_get_log_stats")),
    ("npg_post_log validator accepts stream",
     'log_type not in ("access", "error", "modsec", "stream")' in src),
    ("confirm_no_proxy whitelisted",
     '"confirm_no_proxy"' in open(UM, encoding="utf-8").read()),
]
for label, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        fails.append(label)

print()
if fails:
    print("FAILURES:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("ALL STATIC CHECKS PASSED")
