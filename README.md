# Audio insights with `ai_transcribe` on Databricks

Turn call recordings into structured insights with nothing but SQL. A serverless Lakeflow pipeline transcribes each new
audio file with the built-in [`ai_transcribe`](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_transcribe)
function (Beta), splits it into speaker-labelled segments, and uses `ai_extract` and `ai_analyze_sentiment` to pull out
a summary, customer and agent sentiment, the call reason, resolution and follow-up, plus each speaker's share of the
talk time.

> Sample code provided as-is for evaluation. It is not an official Databricks product and is not supported by
> Databricks.

## How it works

```
raw_audio volume   (mp3 · wav · flac · opus · m4a, any subfolder)
  │  each new file is picked up once
  ▼
audio_transcripts_raw    ai_transcribe(content) → time-stamped, speaker-labelled segments
  ├─▶ transcript_segments    one row per speaker turn
  ├─▶ call_transcripts       "Speaker 1: … / Speaker 2: …" per file; failed files are kept with their error
  │     └─▶ call_insights    ai_analyze_sentiment + ai_extract → summary, customer and agent sentiment,
  │                          agent_speaker_id, call_reason, resolution_status, follow_up_required, key_topics
  └─▶ speaker_sentiment      per speaker: talk seconds, share of talk time, sentiment
```

All five tables are streaming tables. Every AI function runs once per file and its result is stored, so querying the
tables never re-runs the AI. The pipeline definition lives in `resources/audio_insights.yml` and the SQL in
`transformations/`.

## Before you start

- **Turn on the preview.** A workspace admin enables **AI Transcribe** on the workspace **Previews** page.
- **Check your region.** `ai_transcribe` is available in some regions only. See AI function availability for
  [AWS](https://docs.databricks.com/aws/en/resources/feature-region-support#ai-functions-aws),
  [Azure](https://learn.microsoft.com/azure/databricks/resources/feature-region-support) and
  [Google Cloud](https://docs.databricks.com/gcp/en/resources/feature-region-support).
  This repo was tested on AWS (us-east-1).
  - Regions marked ⥂ work only with **cross-Geo processing**, which means your audio is processed outside your workspace's
    Geo. On AWS this includes Tokyo, Seoul, Singapore, Sydney and Mumbai.
  - Cross-Geo processing is on by default outside the US and EU, unless the workspace uses the compliance security profile.
  - An account admin controls it with the **Enforce data processing within workspace Geography for Designated Services**
    setting; see [Databricks Geos](https://docs.databricks.com/aws/en/resources/databricks-geos).
  - The same table shows where the transcript text is processed by the other functions this pipeline uses: `ai_extract`,
    and `ai_analyze_sentiment` under **Other AI functions (v1)**. In some regions those need cross-Geo processing too.
  - Check this against your data-residency requirements before you use real recordings.
- **Mind the Beta limits:**
  - English and Spanish audio only.
  - Up to 1 hour and 512 MB per file.
  - Audio only: MP3, WAV, FLAC, Opus or M4A. For a video, extract the audio track first, for example
    `ffmpeg -i meeting.mp4 -vn -c:a copy meeting.m4a`.
- **Workspace:**
  - Unity Catalog.
  - Serverless compute for Lakeflow pipelines.
  - A serverless SQL warehouse for the queries.
  - `USE CATALOG` and `CREATE SCHEMA` on an existing catalog.
- **Your machine:**
  - The [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install) v0.253.0 or later (tested with v1.17.0),
    logged in with `databricks auth login --host <workspace-url> --profile <profile>`.
  - Python 3.8 or later for the optional check script.

## Two-minute smoke test (optional)

To try `ai_transcribe` before deploying anything, upload `samples/calls/call-20261020-1047.mp3` to any volume you can
write to (Catalog Explorer → your volume → **Upload to this volume**). Then run this in the SQL editor:

```sql
SELECT path, ai_transcribe(content) AS transcription
FROM read_files('/Volumes/<catalog>/<schema>/<volume>/call-20261020-1047.mp3', format => 'binaryFile');
```

## Quickstart (about 15 minutes)

1. **Deploy.** The bundle creates a new schema `audio_insights_demo` (pick another name with `--var schema=<name>`), a
   `raw_audio` volume and the pipeline in the catalog you name:

   ```bash
   git clone https://github.com/germaineong/databricks-audio-insights.git
   cd databricks-audio-insights
   databricks bundle deploy --var catalog=<your_catalog> -p <profile>
   ```

   Every bundle command needs the catalog. To avoid repeating it, run `export BUNDLE_VAR_catalog=<your_catalog>`
   (PowerShell: `$env:BUNDLE_VAR_catalog="<your_catalog>"`; cmd.exe: `set BUNDLE_VAR_catalog=<your_catalog>`) once per
   terminal.

   If you pick another schema name, pass the same `--var schema=<name>` to every bundle command, or also set
   `BUNDLE_VAR_schema=<name>`, and use that name instead of `audio_insights_demo` in the paths and queries below. To
   switch to a different name later, run `bundle destroy` first. Use a dedicated schema: `bundle destroy` drops it with
   everything in it.

2. **Upload the three sample calls:**

   ```bash
   databricks fs cp -r samples/calls dbfs:/Volumes/<your_catalog>/audio_insights_demo/raw_audio/calls -p <profile>
   ```

3. **Run the pipeline.** It takes one to two minutes, and the command prints a link to the run:

   ```bash
   databricks bundle run audio_insights --var catalog=<your_catalog> -p <profile>
   ```

4. **Look at the results** in the SQL editor:

   ```sql
   -- One row per call
   SELECT regexp_extract(path, '[^/]+$', 0) AS file, call_reason, resolution_status, follow_up_required,
          customer_sentiment, agent_sentiment, summary
   FROM <your_catalog>.audio_insights_demo.call_insights;

   -- Which speaker is the agent, and who did the talking?
   SELECT regexp_extract(i.path, '[^/]+$', 0) AS file, s.speaker_id,
          s.speaker_id = i.agent_speaker_id AS is_agent, s.talk_share, s.sentiment
   FROM <your_catalog>.audio_insights_demo.call_insights i
   JOIN <your_catalog>.audio_insights_demo.speaker_sentiment s ON s.path = i.path
   ORDER BY file, s.speaker_id;

   -- The speaker timeline of one call
   SELECT segment_index, start_seconds, end_seconds, speaker_id, text
   FROM <your_catalog>.audio_insights_demo.transcript_segments
   WHERE path LIKE '%call-20261020-1047.mp3'
   ORDER BY segment_index;
   ```

5. **Optional: check the results automatically.** Use the ID of any SQL warehouse:

   ```bash
   python3 scripts/check_synthetic_calls.py <profile> <warehouse_id> <your_catalog>.audio_insights_demo
   ```

   On Windows, run `py scripts\check_synthetic_calls.py …` instead of `python3 …`.

## The sample calls

All three calls, and the spare, are synthetic. They were scripted for this repo and voiced with macOS text-to-speech.
"Acme Telecom" and every name and number in them are fictional. The file names are deliberately neutral, so the call
type has to come from the conversation.

| File | Scenario | What the pipeline should find |
|---|---|---|
| `samples/calls/call-20261020-0912.mp3` (2:05) | Billing dispute. The agent calls the customer back, so the customer speaks first | billing · resolved · the agent is speaker 2 |
| `samples/calls/call-20261020-1047.mp3` (2:58) | Fibre outage | technical_issue · escalated · follow-up needed · negative customer |
| `samples/calls/call-20261020-1405.mp3` (2:13) | Cancellation after outages and price rises | cancellation · resolved |
| `samples/spare/call-20261020-1530.mp3` (1:53) | A happy customer upgrades to a family bundle | sales · resolved |

Keep `samples/spare/call-20261020-1530.mp3` back to show a new file arriving: upload it, run the pipeline again, and only
that file is processed. `samples/manifest.json` lists every call with its voices and expected results.
`scripts/make_synthetic_calls.py` regenerates the audio on a Mac with ffmpeg and the seven voices it names installed. It
overwrites the files in `samples/`, and `say` output can differ between macOS versions, so regenerated calls may not
reproduce the expected results exactly; restore the shipped files with `git checkout -- samples/`.

## Your own recordings

- **Upload** to the `raw_audio` volume (Catalog Explorer → **Upload to this volume**, or `databricks fs cp`), then run
  the pipeline again. Only new files are processed.
- **Re-uploading** a file to the same path (same folder and name) does not process it again, but the same recording in
  another folder counts as a new file. Files with other extensions, including video, are ignored. Extensions can be
  lower- or upper-case (`.wav` or `.WAV`), but not mixed like `.Wav`.
- **Change what gets extracted** by editing the JSON schema and labels in `transformations/call_insights.sql`. Then run
  `databricks bundle deploy --var catalog=<your_catalog> -p <profile>` and reprocess just that table:
  `databricks bundle run audio_insights --full-refresh call_insights --var catalog=<your_catalog> -p <profile>`.
- **Reprocess everything** with `--full-refresh-all`. This re-runs every AI call and replaces the earlier results.

## Costs

- `ai_transcribe` is **free during the Beta**, with pricing to be announced. In our Beta tests it added
  no rows to `system.billing.usage`; once it's priced, it bills under the `AI_FUNCTIONS` product. See
  [Beta products pricing](https://www.databricks.com/product/pricing/beta-products).
- `ai_extract` is billed under `AI_FUNCTIONS`, and `ai_analyze_sentiment` under `MODEL_SERVING` (batch inference). See
  [AI Functions pricing](https://www.databricks.com/product/pricing/ai-functions).
- The pipeline runs on serverless Lakeflow pipelines compute. See
  [Lakeflow Pipelines pricing](https://www.databricks.com/product/pricing/lakeflow-pipelines).
- The SQL warehouse you use for the smoke test, the queries and the check script is billed as serverless SQL while it
  runs, including its idle time before auto-stop. `scripts/test_transforms.py` also makes a few small, billed
  `ai_extract` and `ai_analyze_sentiment` calls on it.
- **Indicative cost:** in our tests on AWS us-east-1, one 5-minute call cost about US$0.11 at list price, end to end.
  Your price depends on cloud, region, tier and contract.

To see what your test cost (needs access to the `system.billing` tables; usage rows appear a few hours after a run),
take the pipeline ID from the end of the pipeline URL that
`databricks bundle summary --var catalog=<your_catalog> -p <profile>` prints:

```sql
SELECT u.billing_origin_product, u.sku_name, ROUND(SUM(u.usage_quantity), 3) AS dbus,
       ROUND(SUM(u.usage_quantity * p.pricing.effective_list.default), 2) AS list_usd
FROM system.billing.usage u
JOIN system.billing.list_prices p
  ON u.cloud = p.cloud AND u.sku_name = p.sku_name AND u.usage_unit = p.usage_unit
 AND u.usage_end_time >= p.price_start_time
 AND (p.price_end_time IS NULL OR u.usage_end_time < p.price_end_time)
WHERE u.usage_metadata.dlt_pipeline_id = '<pipeline_id>'
GROUP BY ALL;
```

## Things to know

- **Speaker labels.** Speakers are numbered "1", "2", … in the order they first speak. `agent_speaker_id` is the
  model's reading of the conversation.
- **Unlabelled fragments.** Very short fragments can come back without a speaker. They show as `Speaker ?` and are not
  counted as a speaker.
- **Segments are speaker turns, not sentences.**
- **Names and product terms** can be spelled inconsistently. There is no custom vocabulary.
- **Reprocessing changes results.** Fields written by the model can come out slightly different if you reprocess.
- **Deleting a recording doesn't delete its transcript.** Rows already in the five tables stay until you reprocess with
  `--full-refresh-all` or run `bundle destroy`, so keep that in mind for real or sensitive recordings.
- **Failed files.** A file that fails to transcribe keeps its error in `call_transcripts.transcribe_error` and is
  skipped downstream.

## Clean up

```bash
databricks bundle destroy --var catalog=<your_catalog> -p <profile>
```

This removes the pipeline, the schema with all five tables and anything else you created in it, and the volume with every
uploaded file.

## Repository layout

| Path | What it is |
|---|---|
| `databricks.yml`, `resources/audio_insights.yml` | The bundle: variables, schema, volume and pipeline |
| `transformations/` | The five pipeline tables, one SQL file each |
| `samples/` | Synthetic calls (`calls/` to upload, `spare/` to keep back) and `manifest.json` |
| `scripts/check_synthetic_calls.py` | Checks the deployed results against the expected values in `scripts/make_synthetic_calls.py`, also listed in `samples/manifest.json` |
| `scripts/test_transforms.py` | Dry-runs the silver and gold SQL on a SQL warehouse against a synthetic transcript: `python3 scripts/test_transforms.py <profile> <warehouse_id>`. It makes a few small, billed AI calls |
| `scripts/make_synthetic_calls.py` | Regenerates the sample audio (macOS `say` + ffmpeg) |
| `scripts/run_sql.py` | Small helper the scripts use to run SQL on a warehouse |

## License

Apache License 2.0. See `LICENSE`.
