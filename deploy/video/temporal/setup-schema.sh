#!/bin/sh
set -eu
for database in temporal temporal_visibility; do
  temporal-sql-tool -p 5432 --plugin postgres12 --ep "$POSTGRES_SEEDS" -u "$POSTGRES_USER" --db "$database" setup-schema -v 0.0
done
temporal-sql-tool -p 5432 --plugin postgres12 --ep "$POSTGRES_SEEDS" -u "$POSTGRES_USER" --db temporal update-schema -d /etc/temporal/schema/postgresql/v12/temporal/versioned
temporal-sql-tool -p 5432 --plugin postgres12 --ep "$POSTGRES_SEEDS" -u "$POSTGRES_USER" --db temporal_visibility update-schema -d /etc/temporal/schema/postgresql/v12/visibility/versioned
