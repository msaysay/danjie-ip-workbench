-- StoryCue interview link and returned transcript for one confirmed topic.
-- Keys never belong in this table. script text and the interview export do.
CREATE TABLE IF NOT EXISTS storycue_link (
  topic_id TEXT PRIMARY KEY,
  handoff_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  framework TEXT NOT NULL,
  script_sha256 TEXT NOT NULL,
  background TEXT NOT NULL,
  open_url TEXT NOT NULL,
  demo INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  result_json TEXT,
  imported_at TEXT
);
