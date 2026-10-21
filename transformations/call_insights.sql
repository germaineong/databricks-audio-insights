-- Gold: overall sentiment (ai_analyze_sentiment) + structured call fields (ai_extract v2.1).
-- In v2.1 every extracted scalar comes back as {"value": ...}, hence the .value paths.
-- The model sometimes answers "Speaker 1" rather than "1" for agent_speaker_id, so only the number is kept.
CREATE OR REFRESH STREAMING TABLE call_insights
COMMENT 'One row per call: sentiment and structured fields extracted from the transcript'
AS SELECT
  path,
  duration_seconds,
  num_speakers,
  ai_analyze_sentiment(transcript) AS overall_sentiment,
  x:response.summary.value::STRING AS summary,
  x:response.customer_sentiment.value::STRING AS customer_sentiment,
  x:response.agent_sentiment.value::STRING AS agent_sentiment,
  nullif(regexp_extract(x:response.agent_speaker_id.value::STRING, '([0-9]+)', 1), '') AS agent_speaker_id,
  x:response.call_reason.value::STRING AS call_reason,
  x:response.resolution_status.value::STRING AS resolution_status,
  x:response.follow_up_required.value::BOOLEAN AS follow_up_required,
  transform(variant_get(x, '$.response.key_topics', 'ARRAY<VARIANT>'), t -> t:value::STRING) AS key_topics,
  x:error_message::STRING AS extract_error
FROM (
  SELECT
    *,
    ai_extract(
      transcript,
      '{
        "summary": {"type": "string", "description": "2-3 sentence summary of the conversation"},
        "customer_sentiment": {"type": "enum", "labels": ["positive", "neutral", "negative", "mixed", "not_applicable"],
                               "description": "Sentiment of the customer / caller"},
        "agent_sentiment": {"type": "enum", "labels": ["positive", "neutral", "negative", "mixed", "not_applicable"],
                            "description": "Sentiment of the agent / company representative"},
        "agent_speaker_id": {"type": "string", "description": "Speaker label (for example 1) of the agent, or none"},
        "call_reason": {"type": "enum", "labels": ["billing", "technical_issue", "complaint", "cancellation",
                                                   "general_enquiry", "sales", "other"]},
        "resolution_status": {"type": "enum", "labels": ["resolved", "unresolved", "escalated", "not_applicable"]},
        "follow_up_required": {"type": "boolean"},
        "key_topics": {"type": "array", "items": {"type": "string"}, "description": "Up to 5 main topics discussed"}
      }',
      map(
        'version', '2.1',
        'instructions', 'The input is a transcript of a recorded conversation, such as a customer service call. Speaker labels come from automatic diarization; work out from context which speaker is the agent. Use not_applicable when a field does not fit the recording.'
      )
    ) AS x
  FROM STREAM(call_transcripts)
  WHERE transcribe_error IS NULL AND transcript IS NOT NULL
);
