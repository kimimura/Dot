-- A format keeps how its sheet is made: the plain columns a model reads, then the user's steps replayed in code.

IF COL_LENGTH('profiles', 'recipe_json') IS NULL
ALTER TABLE profiles ADD recipe_json NVARCHAR(MAX) NULL;
GO
