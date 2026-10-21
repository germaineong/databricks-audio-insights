-- Gold: per-speaker talk time and sentiment. Row-level (no GROUP BY), so it stays a streaming table
-- and each speaker's text is scored by ai_analyze_sentiment exactly once.
CREATE OR REFRESH STREAMING TABLE speaker_sentiment
COMMENT 'One row per call x speaker: talk time, share of talk time and ai_analyze_sentiment of their turns'
AS SELECT
  path,
  speaker_id,
  round(talk_seconds, 1) AS talk_seconds,
  round(talk_seconds / duration_seconds, 3) AS talk_share,
  ai_analyze_sentiment(speaker_text) AS sentiment
FROM (
  SELECT
    path,
    duration_seconds,
    spk AS speaker_id,
    aggregate(filter(segs, s -> s:speaker_id::STRING = spk), 0D,
              (acc, s) -> acc + s:end::DOUBLE - s:start::DOUBLE) AS talk_seconds,
    array_join(transform(filter(segs, s -> s:speaker_id::STRING = spk), s -> s:text::STRING), ' ') AS speaker_text
  FROM (
    SELECT
      path,
      transcription:response.duration_seconds::DOUBLE AS duration_seconds,
      segs,
      explode(array_distinct(filter(transform(segs, s -> s:speaker_id::STRING), id -> id IS NOT NULL))) AS spk
    FROM (
      SELECT path, transcription, variant_get(transcription, '$.response.segments', 'ARRAY<VARIANT>') AS segs
      FROM STREAM(audio_transcripts_raw)
      WHERE transcription:error_message::STRING IS NULL
    )
  )
);
