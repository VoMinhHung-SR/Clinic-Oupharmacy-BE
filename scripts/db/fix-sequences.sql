DO $$
DECLARE
  r RECORD;
  seq_name text;
  max_val bigint;
  tbl_qualified text;
BEGIN
  FOR r IN
    SELECT table_schema, table_name, column_name
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND column_default IS NOT NULL
      AND column_default LIKE 'nextval(%'
  LOOP
    tbl_qualified := r.table_schema || '.' || r.table_name;
    seq_name := pg_get_serial_sequence(tbl_qualified, r.column_name);
    IF seq_name IS NOT NULL THEN
      EXECUTE format('SELECT COALESCE(MAX(%I), 1) FROM %I.%I', r.column_name, r.table_schema, r.table_name) INTO max_val;
      EXECUTE format('SELECT setval(%L, %s)', seq_name, max_val);
    END IF;
  END LOOP;
END $$;
