"""Dry-run the silver/gold transformation files on a SQL warehouse against a synthetic ai_transcribe() result.

Strips each file's CREATE ... AS header and swaps its STREAM(...) source for synthetic rows that follow the
documented ai_transcribe output schema (one good call with an unlabelled fragment + one failed file), so the
exact SQL in the files is exercised without needing the AI Transcribe preview.

Usage: python3 test_transforms.py <profile> <warehouse_id>
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRANSFORMS = ROOT / "transformations"

SYNTHETIC_RAW = """(
  SELECT 'synthetic://test-call.mp3' AS path, 1234 AS file_size_bytes,
         current_timestamp() AS file_modified_at, current_timestamp() AS transcribed_at,
         parse_json('{"error_message": null, "response": {"duration_seconds": 42.5, "segments": [
           {"start": 0.0, "end": 6.2, "speaker_id": "1", "text": "Thank you for calling Acme Telecom, this is Priya. How can I help you today?"},
           {"start": 6.5, "end": 15.0, "speaker_id": "2", "text": "Hi, I was charged twice for my mobile plan this month and I am really frustrated."},
           {"start": 15.0, "end": 15.3, "speaker_id": null, "text": "So"},
           {"start": 15.3, "end": 30.1, "speaker_id": "1", "text": "I am sorry about that. I can see the duplicate charge and I have issued a refund, it will show in three to five business days."},
           {"start": 30.4, "end": 42.5, "speaker_id": "2", "text": "Okay, great, thanks for sorting that out so quickly."}]}}') AS transcription
  UNION ALL
  SELECT 'synthetic://too-long.mp3', 99, current_timestamp(), current_timestamp(),
         parse_json('{"error_message": "Audio exceeds the 1 hour limit", "response": null}')
)"""


def body(name):
    """Return the SELECT body of a transformation file, without comments or the CREATE ... AS header."""
    sql = (TRANSFORMS / f"{name}.sql").read_text()
    sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return re.sub(r"(?is)^.*?\bAS\s+SELECT\b", "SELECT", sql, count=1).strip().rstrip(";")


def run(profile, warehouse, label, sql):
    print(f"\n===== {label}", flush=True)
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_sql.py"), profile, warehouse, "-"],
                         input=sql, text=True)
    if res.returncode != 0:
        sys.exit(f"{label} FAILED")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    profile, warehouse = sys.argv[1], sys.argv[2]
    raw = SYNTHETIC_RAW
    transcripts = "(" + body("call_transcripts").replace("STREAM(audio_transcripts_raw)", raw) + ")"
    run(profile, warehouse, "transcript_segments",
        body("transcript_segments").replace("STREAM(audio_transcripts_raw)", raw))
    run(profile, warehouse, "call_transcripts", transcripts[1:-1])
    run(profile, warehouse, "speaker_sentiment",
        body("speaker_sentiment").replace("STREAM(audio_transcripts_raw)", raw))
    run(profile, warehouse, "call_insights",
        body("call_insights").replace("STREAM(call_transcripts)", transcripts))


if __name__ == "__main__":
    main()
