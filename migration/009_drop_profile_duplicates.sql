-- One of each: a format's date is updated_at (when the user last edited it), and how many files it was confirmed with
-- is n_docs in its fingerprint. The copies of those go.

IF COL_LENGTH('profiles', 'last_edited') IS NOT NULL
BEGIN
    EXEC('UPDATE profiles SET updated_at = last_edited WHERE last_edited IS NOT NULL');
    ALTER TABLE profiles DROP COLUMN last_edited;
END
GO

IF COL_LENGTH('profiles', 'last_used_at') IS NOT NULL
BEGIN
    EXEC('UPDATE profiles SET updated_at = last_used_at WHERE last_used_at IS NOT NULL');
    ALTER TABLE profiles DROP COLUMN last_used_at;
END
GO

IF COL_LENGTH('profiles', 'times_used') IS NOT NULL
BEGIN
    DECLARE @default SYSNAME = (SELECT d.name FROM sys.default_constraints d JOIN sys.columns c
                                ON c.default_object_id = d.object_id WHERE c.object_id = OBJECT_ID('profiles') AND c.name = 'times_used');
    IF @default IS NOT NULL EXEC('ALTER TABLE profiles DROP CONSTRAINT ' + @default);
    ALTER TABLE profiles DROP COLUMN times_used;
END
GO
