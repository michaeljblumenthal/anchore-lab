#!/usr/bin/env bash
# Phase 6's headline numbers: total components catalogued and total
# findings across the whole lab, before triage. Queries the same catalogue
# the runtime pipeline (Phase 3) writes to -- no special path for the
# self-scan.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Component inventory ==="
./psql.sh "SELECT count(*) AS images_tracked FROM images;"
./psql.sh "SELECT count(*) AS sboms_stored FROM sboms;"
./psql.sh "SELECT sum(package_count) AS total_packages_catalogued FROM sboms;"

echo
echo "=== Findings, latest scan per image, before any VEX triage ==="
./psql.sh "
SELECT
  count(*) AS total_findings,
  sum(CASE WHEN f.severity = 'Critical' THEN 1 ELSE 0 END) AS critical,
  sum(CASE WHEN f.severity = 'High' THEN 1 ELSE 0 END) AS high,
  sum(CASE WHEN f.severity = 'Medium' THEN 1 ELSE 0 END) AS medium,
  sum(CASE WHEN f.severity = 'Low' THEN 1 ELSE 0 END) AS low,
  sum(CASE WHEN f.severity = 'Negligible' THEN 1 ELSE 0 END) AS negligible
FROM findings f
JOIN scan_results sr ON sr.id = f.scan_result_id
WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id);
"

echo
echo "=== Findings per image, worst first ==="
./psql.sh "
SELECT i.repository, i.tag, sr.total_matches, sr.critical_count, sr.high_count
FROM scan_results sr
JOIN sboms s ON s.id = sr.sbom_id
JOIN images i ON i.id = s.image_id
WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id)
ORDER BY sr.critical_count DESC, sr.high_count DESC;
"

echo
echo "=== Base image / package commonality: which packages appear across the most images ==="
echo "=== (a proxy for 'how many findings would one base image update clear') ==="
./psql.sh "
SELECT f.package_name, count(DISTINCT f.image_id) AS images_affected, count(*) AS total_findings_from_this_package
FROM findings f
JOIN scan_results sr ON sr.id = f.scan_result_id
WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id)
GROUP BY f.package_name
ORDER BY images_affected DESC, total_findings_from_this_package DESC
LIMIT 15;
"

echo
echo "=== Images tracked but never SBOM'd (bootstrap-ordering / coverage gaps) ==="
./psql.sh "
SELECT i.repository, i.tag
FROM images i
LEFT JOIN sboms s ON s.image_id = i.id
WHERE s.id IS NULL;
"
