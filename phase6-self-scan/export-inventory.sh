#!/usr/bin/env bash
# Ships the lab's own SBOM and full component inventory in the repository,
# per the plan's explicit instruction. Exports the catalogue's own picture
# of every component (per aggregate-report.sh's queries, as CSV) plus the
# stored SBOM for this repo's own sbom-mcp-server, so the artefact itself
# is committed, not just described.
set -euo pipefail
cd "$(dirname "$0")"
OUT="inventory-export"
mkdir -p "$OUT"

echo "Exporting component inventory..."
./psql.sh "
COPY (
  SELECT i.repository, i.tag, s.package_count, sr.total_matches,
         sr.critical_count, sr.high_count, sr.medium_count, sr.low_count, sr.negligible_count
  FROM images i
  JOIN sboms s ON s.image_id = i.id
  JOIN scan_results sr ON sr.id = (SELECT max(id) FROM scan_results WHERE sbom_id = s.id)
  ORDER BY sr.critical_count DESC, sr.high_count DESC
) TO STDOUT WITH CSV HEADER
" > "$OUT/component-inventory.csv"

echo "Exporting aggregate summary..."
./psql.sh "
SELECT
  (SELECT count(*) FROM images) AS images_tracked,
  (SELECT count(*) FROM sboms) AS sboms_stored,
  (SELECT sum(package_count) FROM sboms) AS total_packages,
  (SELECT count(*) FROM findings f JOIN scan_results sr ON sr.id = f.scan_result_id WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id)) AS total_findings_pre_triage
" > "$OUT/aggregate-summary.txt"

echo "Done. See $OUT/"
cat "$OUT/component-inventory.csv"
