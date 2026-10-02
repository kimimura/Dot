-- Dot's tables for SQL Server. Safe to re-run: anything that already exists is skipped.
-- New database: CREATE DATABASE DOT_DEV, select it, run this file (SSMS, or: sqlcmd -S server -d DOT_DEV -i migration/001_init.sql)

IF OBJECT_ID('profiles', 'U') IS NULL
CREATE TABLE profiles (
  id NVARCHAR(32) NOT NULL PRIMARY KEY,
  name NVARCHAR(200) NOT NULL UNIQUE,
  created_at NVARCHAR(32),
  updated_at NVARCHAR(32),
  last_used_at NVARCHAR(32),
  columns_json NVARCHAR(MAX) DEFAULT '[]',
  fingerprint_json NVARCHAR(MAX) DEFAULT '{}',
  hints_json NVARCHAR(MAX) DEFAULT '[]',
  examples_json NVARCHAR(MAX) DEFAULT '[]',
  signature_json NVARCHAR(MAX) DEFAULT '{}',
  times_used INT DEFAULT 0
);
GO

IF OBJECT_ID('documents', 'U') IS NULL
CREATE TABLE documents (
  id NVARCHAR(32) NOT NULL PRIMARY KEY,
  filename NVARCHAR(400),
  sha256 NVARCHAR(64),
  size BIGINT,
  n_pages INT,
  uploaded_at NVARCHAR(32),
  confirmed_at NVARCHAR(32),
  stage NVARCHAR(32),
  error NVARCHAR(MAX),
  profile_id NVARCHAR(32) NULL REFERENCES profiles(id) ON DELETE SET NULL,
  has_text_layer BIT DEFAULT 0,
  n_rows INT DEFAULT 0,
  verified_pct FLOAT NULL,
  state_json NVARCHAR(MAX) DEFAULT '{}',
  pdf_data VARBINARY(MAX) NULL
);
GO

IF COL_LENGTH('documents', 'pdf_data') IS NULL
ALTER TABLE documents ADD pdf_data VARBINARY(MAX) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_docs_uploaded')
CREATE INDEX ix_docs_uploaded ON documents(uploaded_at DESC);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_docs_profile')
CREATE INDEX ix_docs_profile ON documents(profile_id);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_docs_sha')
CREATE INDEX ix_docs_sha ON documents(sha256);
GO
