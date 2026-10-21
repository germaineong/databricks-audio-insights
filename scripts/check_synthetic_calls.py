"""Check the synthetic calls end to end: the local MP3s, then what the pipeline extracted from each uploaded call.

Local: every call in make_synthetic_calls.CALLS exists as a mono 16 kHz MP3 of 1-4 minutes (skipped when ffprobe,
part of ffmpeg, isn't installed). Pipeline: each uploaded call has 2 speakers in call_transcripts and the expected
call_reason, resolution_status and agent_speaker_id in call_insights. Exits non-zero if any check fails.

Usage: python3 check_synthetic_calls.py <profile> <warehouse_id> <catalog.schema>
"""
import json
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from make_synthetic_calls import CALLS, ROOT, SAMPLE_RATE, sample_path  # noqa: E402


def probe(path):
    """Return (codec, channels, sample_rate, duration_seconds) of the first audio stream."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=codec_name,channels,sample_rate:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    stream = info["streams"][0]
    return stream["codec_name"], stream["channels"], int(stream["sample_rate"]), float(info["format"]["duration"])


def pipeline_rows(profile, warehouse, schema):
    """Return {file name: [rows]} from call_insights joined to call_transcripts in schema, for the uploaded calls."""
    files = ", ".join(f"'{c['file']}'" for c in CALLS if c["upload"])
    sql = f"""SELECT regexp_extract(i.path, '[^/]+$', 0) AS file, t.num_speakers,
       i.call_reason, i.resolution_status, i.agent_speaker_id
FROM {schema}.call_insights i JOIN {schema}.call_transcripts t ON t.path = i.path
WHERE regexp_extract(i.path, '[^/]+$', 0) IN ({files})"""
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_sql.py"), profile, warehouse, "-"],
                         input=sql, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"query failed: {res.stderr.strip()}")
    rows = {}
    for row in map(json.loads, res.stdout.splitlines()):
        rows.setdefault(row["file"], []).append(row)
    return rows


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    profile, warehouse, schema = sys.argv[1:4]
    parts = schema.split(".")
    if len(parts) != 2 or not all(parts):
        sys.exit(f"expected <catalog>.<schema>, got {schema!r}\n\n{__doc__}")
    schema = ".".join(f"`{part}`" for part in parts)
    failures = []

    def check(ok, label):
        print(f"{'PASS' if ok else 'FAIL'}  {label}", flush=True)
        if not ok:
            failures.append(label)

    have_ffprobe = shutil.which("ffprobe") is not None
    for call in CALLS:
        path = sample_path(call)
        if not have_ffprobe:
            print(f"SKIP  {call['file']}: local format check (ffprobe not found; install ffmpeg to run it)", flush=True)
            continue
        if not path.exists():
            check(False, f"{call['file']}: exists in {path.parent.relative_to(ROOT)}/")
            continue
        codec, channels, rate, duration = probe(path)
        check(codec == "mp3" and channels == 1 and rate == SAMPLE_RATE and 60 <= duration <= 240,
              f"{call['file']}: mono {SAMPLE_RATE} Hz MP3 of 1-4 min (got {codec}, {channels} ch, {rate} Hz, "
              f"{duration:.0f} s)")

    rows = pipeline_rows(profile, warehouse, schema)
    for call in (c for c in CALLS if c["upload"]):
        found = rows.get(call["file"], [])
        if not found:
            check(False, f"{call['file']}: processed by the pipeline")
            continue
        if len(found) > 1:
            check(False, f"{call['file']}: exactly one row (got {len(found)}; uploaded to more than one folder?)")
            continue
        row = found[0]
        check(row["num_speakers"] == "2", f"{call['file']}: 2 speakers (got {row['num_speakers']})")
        for field, want in call["expected"].items():
            check(row[field] == want, f"{call['file']}: {field} = {want} (got {row[field]})")

    print(f"\n{len(failures)} check(s) failed" if failures else "\nall checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
