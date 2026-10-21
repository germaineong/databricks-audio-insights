"""Run a SQL statement on a Databricks SQL warehouse via the Statement Execution API and poll until done.

Usage: python3 run_sql.py <profile> <warehouse_id> <sql_file_or_->
Prints the result rows as JSON (one object per row).
"""
import json
import subprocess
import sys
import time


def api(profile, method, path, body=None):
    cmd = ["databricks", "api", method, path, "--profile", profile]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"API error: {out.stderr.strip() or out.stdout.strip()}")
    return json.loads(out.stdout)


def main():
    profile, warehouse_id, src = sys.argv[1], sys.argv[2], sys.argv[3]
    statement = sys.stdin.read() if src == "-" else open(src).read()
    resp = api(profile, "post", "/api/2.0/sql/statements/", {
        "statement": statement,
        "warehouse_id": warehouse_id,
        "format": "JSON_ARRAY",
        "disposition": "INLINE",
        "wait_timeout": "50s",
        "on_wait_timeout": "CONTINUE",
    })
    sid = resp["statement_id"]
    started = time.time()
    while resp["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(10)
        resp = api(profile, "get", f"/api/2.0/sql/statements/{sid}")
        print(f"... {resp['status']['state']} ({int(time.time() - started)}s)", file=sys.stderr)
    state = resp["status"]["state"]
    if state != "SUCCEEDED":
        sys.exit(f"{state}: {json.dumps(resp['status'].get('error', resp['status']), indent=2)}")
    cols = [c["name"] for c in resp["manifest"]["schema"]["columns"]]
    for row in resp.get("result", {}).get("data_array", []) or []:
        print(json.dumps(dict(zip(cols, row)), ensure_ascii=False))
    print(f"[{state} in {int(time.time() - started)}s, statement_id={sid}]", file=sys.stderr)


if __name__ == "__main__":
    main()
