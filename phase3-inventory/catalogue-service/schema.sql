-- Catalogue schema: maps discovered images to stored SBOMs, and stores the
-- most recent Grype re-match result per image so "is this CVE present and
-- reachable" can be answered by a query, not a rescan.

CREATE TABLE IF NOT EXISTS images (
    id              SERIAL PRIMARY KEY,
    digest          TEXT NOT NULL UNIQUE,
    repository      TEXT NOT NULL,
    tag             TEXT,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- populated by the runtime-inventory job; NULL until confirmed running
    running_in      JSONB
);

CREATE INDEX IF NOT EXISTS idx_images_repository ON images (repository);

CREATE TABLE IF NOT EXISTS sboms (
    id              SERIAL PRIMARY KEY,
    image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    format          TEXT NOT NULL DEFAULT 'syft-json',
    minio_bucket    TEXT NOT NULL,
    minio_key       TEXT NOT NULL,
    package_count   INTEGER,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    syft_version    TEXT,
    UNIQUE (image_id, format)
);

CREATE TABLE IF NOT EXISTS scan_results (
    id              SERIAL PRIMARY KEY,
    sbom_id         INTEGER NOT NULL REFERENCES sboms(id) ON DELETE CASCADE,
    scanned_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    grype_version   TEXT,
    grype_db_built  TIMESTAMPTZ,
    total_matches   INTEGER NOT NULL,
    critical_count  INTEGER NOT NULL DEFAULT 0,
    high_count      INTEGER NOT NULL DEFAULT 0,
    medium_count    INTEGER NOT NULL DEFAULT 0,
    low_count       INTEGER NOT NULL DEFAULT 0,
    negligible_count INTEGER NOT NULL DEFAULT 0,
    raw_result      JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scan_results_sbom_id ON scan_results (sbom_id);
CREATE INDEX IF NOT EXISTS idx_scan_results_scanned_at ON scan_results (scanned_at);

-- One row per (image, CVE) pulled out of scan_results.raw_result, so "which
-- running images contain CVE-X" is an indexed lookup, not a JSONB scan of
-- every stored result. Populated by the re-matching job alongside
-- scan_results, not derived lazily.
CREATE TABLE IF NOT EXISTS findings (
    id              SERIAL PRIMARY KEY,
    scan_result_id  INTEGER NOT NULL REFERENCES scan_results(id) ON DELETE CASCADE,
    image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    vulnerability_id TEXT NOT NULL,
    severity        TEXT NOT NULL,
    package_name    TEXT NOT NULL,
    package_version TEXT,
    fix_state       TEXT,
    vex_status      TEXT  -- null until a VEX statement is applied
);

CREATE INDEX IF NOT EXISTS idx_findings_vuln_id ON findings (vulnerability_id);
CREATE INDEX IF NOT EXISTS idx_findings_image_id ON findings (image_id);
