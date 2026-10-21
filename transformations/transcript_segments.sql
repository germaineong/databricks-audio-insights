-- Silver: one row per diarized segment, for timeline / talk-pattern analytics.
CREATE OR REFRESH STREAMING TABLE transcript_segments
COMMENT 'One row per transcript segment: speaker label, start/end seconds and text'
AS SELECT
  path,
  segment_index,
  seg:start::DOUBLE AS start_seconds,
  seg:end::DOUBLE AS end_seconds,
  seg:speaker_id::STRING AS speaker_id,
  seg:text::STRING AS text
FROM (
  SELECT
    path,
    posexplode(variant_get(transcription, '$.response.segments', 'ARRAY<VARIANT>')) AS (segment_index, seg)
  FROM STREAM(audio_transcripts_raw)
  WHERE transcription:error_message::STRING IS NULL
);
