-- Email intake: each email's PDFs share its id as their batch, and the results go back once they are all done.

IF OBJECT_ID('email_requests', 'U') IS NULL
CREATE TABLE email_requests (
  id NVARCHAR(32) NOT NULL PRIMARY KEY,
  sender NVARCHAR(320),
  received_at NVARCHAR(32),
  stamp NVARCHAR(32),
  doc_ids_json NVARCHAR(MAX) DEFAULT '[]',
  status NVARCHAR(16),
  error NVARCHAR(MAX),
  sent_at NVARCHAR(32)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_email_requests_status')
CREATE INDEX ix_email_requests_status ON email_requests(status);
GO
