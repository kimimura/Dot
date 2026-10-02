-- Bulk conversion: which upload batch a document came in with, and how its format was chosen.

IF COL_LENGTH('documents', 'batch_id') IS NULL
ALTER TABLE documents ADD batch_id NVARCHAR(32) NULL;
GO

IF COL_LENGTH('documents', 'auto_how') IS NULL
ALTER TABLE documents ADD auto_how NVARCHAR(40) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_docs_batch')
CREATE INDEX ix_docs_batch ON documents(batch_id);
GO
