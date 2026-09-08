#!/usr/bin/env bash
# Generate SBOMs in all three formats for an image, then scan for
# vulnerabilities with and without the matching VEX document (if present).
# Usage: ./scan-image.sh <image-ref> [vex-file]
set -euo pipefail

IMAGE="${1:?usage: scan-image.sh <image-ref> [vex-file]}"
VEX="${2:-}"
export DOCKER_HOST="${DOCKER_HOST:-unix://$HOME/.colima/default/docker.sock}"

cd "$(dirname "$0")"
mkdir -p sboms scans

SAFE_NAME=$(echo "$IMAGE" | tr '/:' '__')

for fmt in syft-json spdx-json cyclonedx-json; do
  echo "==> syft scan docker:$IMAGE -o $fmt"
  start=$(date +%s.%N)
  syft scan "docker:$IMAGE" -o "$fmt" > "sboms/${SAFE_NAME}.${fmt}.json"
  end=$(date +%s.%N)
  echo "    duration: $(echo "$end - $start" | bc)s, size: $(wc -c < "sboms/${SAFE_NAME}.${fmt}.json") bytes"
done

echo "==> grype sbom:${SAFE_NAME}.syft-json.json"
grype "sbom:sboms/${SAFE_NAME}.syft-json.json" -o json > "scans/${SAFE_NAME}.grype.json"
python3 -c "
import json
r = json.load(open('scans/${SAFE_NAME}.grype.json'))
print('matches:', len(r['matches']))
"

if [ -n "$VEX" ]; then
  echo "==> grype sbom:${SAFE_NAME}.syft-json.json --vex $VEX"
  grype "sbom:sboms/${SAFE_NAME}.syft-json.json" --vex "$VEX" -o json > "scans/${SAFE_NAME}.grype.vex.json"
  python3 -c "
import json
r = json.load(open('scans/${SAFE_NAME}.grype.vex.json'))
print('matches after VEX:', len(r['matches']), '| ignored:', len(r.get('ignoredMatches', [])))
"
fi
