#!/usr/bin/env bash
set -euo pipefail

DB_HOST="localhost"
DB_PORT="5432"
DB_USER="kit"
DB_NAME="knightindustrytech"

echo "⚠️  RESETTING PRODUCT TABLES IN ${DB_NAME}"
echo "------------------------------------------"

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<'SQL'
BEGIN;

-- =========================
-- PRODUCTS
-- =========================
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'products'
      AND column_name NOT IN ('id', 'external_id')
  LOOP
    EXECUTE format(
      'ALTER TABLE products DROP COLUMN IF EXISTS %I CASCADE;',
      r.column_name
    );
  END LOOP;

  TRUNCATE TABLE products RESTART IDENTITY CASCADE;
END
$$;

-- =========================
-- PRODUCT VARIANTS
-- =========================
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'product_variants'
      AND column_name NOT IN ('id', 'external_id')
  LOOP
    EXECUTE format(
      'ALTER TABLE product_variants DROP COLUMN IF EXISTS %I CASCADE;',
      r.column_name
    );
  END LOOP;

  TRUNCATE TABLE product_variants RESTART IDENTITY CASCADE;
END
$$;

-- =========================
-- PRODUCT OPTIONS
-- =========================
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'product_options'
      AND column_name NOT IN ('id', 'external_id')
  LOOP
    EXECUTE format(
      'ALTER TABLE product_options DROP COLUMN IF EXISTS %I CASCADE;',
      r.column_name
    );
  END LOOP;

  TRUNCATE TABLE product_options RESTART IDENTITY CASCADE;
END
$$;

-- =========================
-- PRODUCT IMAGES
-- =========================
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'product_images'
      AND column_name NOT IN ('id', 'external_id')
  LOOP
    EXECUTE format(
      'ALTER TABLE product_images DROP COLUMN IF EXISTS %I CASCADE;',
      r.column_name
    );
  END LOOP;

  TRUNCATE TABLE product_images RESTART IDENTITY CASCADE;
END
$$;

COMMIT;
SQL

echo "✅ Product tables fully reset."
