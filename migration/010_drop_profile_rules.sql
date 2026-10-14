-- A format's instructions live in its columns' hints; the separate list of rules only repeated them, so it goes.

IF COL_LENGTH('profiles', 'hints_json') IS NOT NULL
BEGIN
    DECLARE @default SYSNAME = (SELECT d.name FROM sys.default_constraints d JOIN sys.columns c
                                ON c.default_object_id = d.object_id WHERE c.object_id = OBJECT_ID('profiles') AND c.name = 'hints_json');
    IF @default IS NOT NULL EXEC('ALTER TABLE profiles DROP CONSTRAINT ' + @default);
    ALTER TABLE profiles DROP COLUMN hints_json;
END
GO
