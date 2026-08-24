import os
import subprocess
import sys

CODE = (
    "import npg_mcp.client as c\n"
    "print('TIMEOUT=', c._HTTP_TIMEOUT)\n"
)

def run_with_env(env_patch):
    env = dict(os.environ)
    if env_patch is None:
        env.pop("NPG_HTTP_TIMEOUT", None)
    else:
        env["NPG_HTTP_TIMEOUT"] = env_patch
    out = subprocess.run(
        [sys.executable, "-c", CODE],
        env=env,
        capture_output=True,
        text=True,
        cwd="/home/four2mis/workspace/npg-mcp",
    )
    return out.stdout.strip()

unset = run_with_env(None)
set60 = run_with_env("60")
bad = run_with_env("abc")
huge = run_with_env("9000")

print("unset  ->", unset)
print("60     ->", set60)
print("abc    ->", bad)
print("9000   ->", huge)

assert "TIMEOUT= 30.0" in unset, unset
assert "TIMEOUT= 60.0" in set60, set60
assert "TIMEOUT= 30.0" in bad, bad
assert "TIMEOUT= 600.0" in huge, huge
print("ENV-IMPORT CHECK PASSED")
