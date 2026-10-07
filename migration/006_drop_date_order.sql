-- Formats no longer keep their own date setting; every date is read day first.

IF COL_LENGTH('profiles', 'date_order') IS NOT NULL
ALTER TABLE profiles DROP COLUMN date_order;
GO
