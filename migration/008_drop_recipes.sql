-- Formats are read by what their layout has learned; the separate saved steps are gone.

IF COL_LENGTH('profiles', 'recipe_json') IS NOT NULL
ALTER TABLE profiles DROP COLUMN recipe_json;
GO
