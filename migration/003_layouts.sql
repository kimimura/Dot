-- Code-first reading: each format's learned row layout, and why a file was read the slower way instead.

IF COL_LENGTH('profiles', 'layout_json') IS NULL
ALTER TABLE profiles ADD layout_json NVARCHAR(MAX) NULL;
GO

IF COL_LENGTH('documents', 'read_note') IS NULL
ALTER TABLE documents ADD read_note NVARCHAR(400) NULL;
GO
