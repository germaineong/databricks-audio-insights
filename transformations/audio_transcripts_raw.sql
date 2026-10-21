-- Bronze: transcribe each new audio file exactly once (Auto Loader tracks which files are done).
-- The source folder is the audio_path value in the pipeline configuration (resources/audio_insights.yml):
-- the whole raw_audio volume, including subfolders. Extensions may be lower- or upper-case.
CREATE OR REFRESH STREAMING TABLE audio_transcripts_raw
COMMENT 'One row per audio file: raw ai_transcribe() output (VARIANT) plus file metadata'
AS SELECT
  path,
  length AS file_size_bytes,
  modificationTime AS file_modified_at,
  current_timestamp() AS transcribed_at,
  ai_transcribe(content) AS transcription
FROM STREAM read_files(
  '${audio_path}',
  format => 'binaryFile',
  fileNamePattern => '*.{mp3,wav,flac,opus,m4a,MP3,WAV,FLAC,OPUS,M4A}'
);
