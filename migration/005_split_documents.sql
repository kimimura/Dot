-- Documents split into their own tables: where each arrived from, its PDF, its conversation and its official output.

-- ── Submissions: one arrival of PDFs (an email, an Upload batch or a Profile Builder drop); every document belongs to one. ────

IF OBJECT_ID('submissions', 'U') IS NULL
CREATE TABLE submissions (
  id NVARCHAR(32) NOT NULL PRIMARY KEY,
  source NVARCHAR(16) NOT NULL,
  sender NVARCHAR(320) NULL,
  received_at NVARCHAR(32) NULL,
  stamp NVARCHAR(32) NULL,
  status NVARCHAR(16) NULL,
  error NVARCHAR(MAX) NULL,
  sent_at NVARCHAR(32) NULL
);
GO

IF COL_LENGTH('documents', 'submission_id') IS NULL
ALTER TABLE documents ADD submission_id NVARCHAR(32) NULL;
GO

IF COL_LENGTH('documents', 'position') IS NULL
ALTER TABLE documents ADD position INT NULL;
GO

-- emails that came in before this table existed keep their id, sender and sending status
IF OBJECT_ID('email_requests', 'U') IS NOT NULL
INSERT INTO submissions(id, source, sender, received_at, stamp, status, error, sent_at)
SELECT e.id, 'email', e.sender, e.received_at, e.stamp, e.status, e.error, e.sent_at FROM email_requests e
WHERE NOT EXISTS (SELECT 1 FROM submissions s WHERE s.id = e.id);
GO

INSERT INTO submissions(id, source, received_at)
SELECT d.batch_id, 'upload', MIN(d.uploaded_at) FROM documents d
WHERE d.batch_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM submissions s WHERE s.id = d.batch_id)
GROUP BY d.batch_id;
GO

UPDATE documents SET submission_id = batch_id WHERE submission_id IS NULL AND batch_id IS NOT NULL;
GO

-- a document dropped into the Profile Builder is a submission of its own, sharing the document's id
INSERT INTO submissions(id, source, received_at)
SELECT d.id, 'builder', d.uploaded_at FROM documents d
WHERE d.submission_id IS NULL AND NOT EXISTS (SELECT 1 FROM submissions s WHERE s.id = d.id);
GO

UPDATE documents SET submission_id = id WHERE submission_id IS NULL;
GO

IF OBJECT_ID('email_requests', 'U') IS NOT NULL
UPDATE d SET d.position = CAST(j.[key] AS INT)
FROM documents d JOIN email_requests e ON e.id = d.submission_id CROSS APPLY OPENJSON(e.doc_ids_json) j
WHERE j.value = d.id AND d.position IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_documents_submission')
ALTER TABLE documents ADD CONSTRAINT fk_documents_submission FOREIGN KEY (submission_id) REFERENCES submissions(id);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_docs_submission')
CREATE INDEX ix_docs_submission ON documents(submission_id);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_submissions_waiting')
CREATE INDEX ix_submissions_waiting ON submissions(source, status);
GO

-- ── Each document's PDF in a table of its own, so lists and searches over documents never carry the file bytes. ────

IF OBJECT_ID('document_files', 'U') IS NULL
CREATE TABLE document_files (
  document_id NVARCHAR(32) NOT NULL PRIMARY KEY,
  pdf_data VARBINARY(MAX) NOT NULL,
  CONSTRAINT fk_document_files_document FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
GO

INSERT INTO document_files(document_id, pdf_data)
SELECT d.id, d.pdf_data FROM documents d
WHERE d.pdf_data IS NOT NULL AND NOT EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = d.id);
GO

-- ── The conversation about each document, one row per message, instead of a list inside the document's saved state. ────

IF OBJECT_ID('messages', 'U') IS NULL
CREATE TABLE messages (
  document_id NVARCHAR(32) NOT NULL,
  seq INT NOT NULL,
  who NVARCHAR(8) NOT NULL,
  text NVARCHAR(MAX) NULL,
  created_at NVARCHAR(32) NULL,
  meta_json NVARCHAR(MAX) NULL,
  CONSTRAINT pk_messages PRIMARY KEY (document_id, seq),
  CONSTRAINT fk_messages_document FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
GO

-- each message keeps what it said and when; anything else it carried (an answer picked, a list of changes) stays as JSON
INSERT INTO messages(document_id, seq, who, text, created_at, meta_json)
SELECT d.id, CAST(t.[key] AS INT), ISNULL(m.who, ''), m.text, m.at,
       JSON_MODIFY(JSON_MODIFY(JSON_MODIFY(t.value, '$.who', NULL), '$.text', NULL), '$.at', NULL)
FROM documents d
CROSS APPLY OPENJSON(d.state_json, '$.transcript') t
CROSS APPLY OPENJSON(t.value) WITH (who NVARCHAR(8) '$.who', text NVARCHAR(MAX) '$.text', at NVARCHAR(32) '$.at') m
WHERE ISJSON(d.state_json) = 1 AND NOT EXISTS (SELECT 1 FROM messages x WHERE x.document_id = d.id);
GO

-- once copied, the old list is taken out of the saved state so it can never be copied a second time
UPDATE d SET d.state_json = JSON_MODIFY(d.state_json, '$.transcript', NULL)
FROM documents d
WHERE ISJSON(d.state_json) = 1 AND JSON_QUERY(d.state_json, '$.transcript') IS NOT NULL
  AND (EXISTS (SELECT 1 FROM messages x WHERE x.document_id = d.id) OR JSON_QUERY(d.state_json, '$.transcript') = '[]');
GO

-- ── The official standard JSON of each processed document: the copy as it was sent, and the current one after any fixes. ────

IF OBJECT_ID('outputs', 'U') IS NULL
CREATE TABLE outputs (
  document_id NVARCHAR(32) NOT NULL,
  version NVARCHAR(8) NOT NULL,
  chain NVARCHAR(200) NULL,
  process_date NVARCHAR(32) NULL,
  json NVARCHAR(MAX) NOT NULL,
  CONSTRAINT pk_outputs PRIMARY KEY (document_id, version),
  CONSTRAINT ck_outputs_version CHECK (version IN ('sent', 'current')),
  CONSTRAINT fk_outputs_document FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
GO

IF COL_LENGTH('profiles', 'date_order') IS NULL
ALTER TABLE profiles ADD date_order NVARCHAR(3) NULL;
GO

-- ── What the split left behind: everything above has been copied out of these, so they go. ────

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_docs_batch' AND object_id = OBJECT_ID('documents'))
DROP INDEX ix_docs_batch ON documents;
GO

IF COL_LENGTH('documents', 'batch_id') IS NOT NULL
ALTER TABLE documents DROP COLUMN batch_id;
GO

IF COL_LENGTH('documents', 'pdf_data') IS NOT NULL
ALTER TABLE documents DROP COLUMN pdf_data;
GO

IF OBJECT_ID('email_requests', 'U') IS NOT NULL
DROP TABLE email_requests;
GO

IF COL_LENGTH('submissions', 'subject') IS NOT NULL
ALTER TABLE submissions DROP COLUMN subject;
GO
