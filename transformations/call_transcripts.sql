-- Silver: one speaker-labelled transcript per call. Failed transcriptions are kept with their error.
-- Diarization leaves some short fragments without a speaker_id: label them '?' and don't count them as a speaker.
CREATE OR REFRESH STREAMING TABLE call_transcripts
COMMENT 'One row per call: duration, segment/speaker counts and the full speaker-labelled transcript'
AS SELECT
  path,
  transcription:response.duration_seconds::DOUBLE AS duration_seconds,
  size(segs) AS num_segments,
  size(array_distinct(filter(transform(segs, s -> s:speaker_id::STRING), id -> id IS NOT NULL))) AS num_speakers,
  array_join(transform(segs, s -> concat('Speaker ', coalesce(s:speaker_id::STRING, '?'), ': ', s:text::STRING)), '\n') AS transcript,
  transcription:error_message::STRING AS transcribe_error
FROM (
  SELECT
    path,
    transcription,
    variant_get(transcription, '$.response.segments', 'ARRAY<VARIANT>') AS segs
  FROM STREAM(audio_transcripts_raw)
);
