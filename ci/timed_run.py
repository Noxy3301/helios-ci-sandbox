"""Run one group of the SQL tests the way test/run_tests.py does, timed.

Usage: timed_run.py <group> <ngroups> <out_dir>. Run from the repo root.
"""
import glob
import json
import os
import shutil
import sys
import time

sys.path.insert(0, "test")
import run_tests as rt  # noqa: E402  (its args global is set only under __main__)

group, ngroups, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
os.makedirs(out, exist_ok=True)

# Same glob and filter as run_tests.main(), sorted, then this group's share.
files = glob.glob(os.path.join("test/pytest", "**", "*.py"), recursive=True)
files = sorted(f for f in files if "/utils/" not in f)
files = [f for i, f in enumerate(files) if i % ngroups == group]


def timed(fn):
  start = time.monotonic()
  value = fn()
  return round(time.monotonic() - start, 2), value


def sh(cmd):
  return os.waitstatus_to_exitcode(os.system(cmd))


wall_start = time.monotonic()
build_s, build_rc = timed(lambda: sh("./scripts/build_partial.sh"))
print(f"TIMING build_partial s={build_s} rc={build_rc}", flush=True)

results = []
if build_rc == 0:
  for f in files:
    print(f"=== BEGIN {f}", flush=True)
    restart_s, _ = timed(rt.restart_services)
    if "/tpc-c/" in f:
      cmd = f"python3 {f} --host {rt.SERVER_HOST} --port {rt.MYSQLD_PORT}"
    else:
      cmd = f"python3 {f}"
    body_s, rc = timed(lambda: sh(cmd))
    # The next restart wipes helios_data, so keep a failing file's logs now.
    if rc != 0 and os.path.isdir("helios_data/logs"):
      shutil.copytree("helios_data/logs", os.path.join(out, "logs", f.replace("/", "_")),
                      dirs_exist_ok=True)
    print(f"TIMING {f} restart={restart_s} body={body_s} rc={rc}", flush=True)
    results.append({"file": f, "restart_s": restart_s, "body_s": body_s, "rc": rc})
  sh(f"./scripts/stop_mysql.sh {rt.QUIET}")
  sh(f"./scripts/stop_server.sh {rt.QUIET}")

failed = [r["file"] for r in results if r["rc"] != 0]
summary = {
  "group": group, "ngroups": ngroups,
  "build_partial_s": build_s, "build_partial_rc": build_rc,
  "files": results,
  "totals": {
    "nfiles": len(results), "nfailed": len(failed), "failed": failed,
    "restart_s": round(sum(r["restart_s"] for r in results), 2),
    "body_s": round(sum(r["body_s"] for r in results), 2),
    "wall_s": round(time.monotonic() - wall_start, 2),
  },
}
with open(os.path.join(out, "timing.json"), "w") as fp:
  json.dump(summary, fp, indent=2)
print(json.dumps(summary["totals"]), flush=True)
sys.exit(1 if build_rc != 0 or failed else 0)
