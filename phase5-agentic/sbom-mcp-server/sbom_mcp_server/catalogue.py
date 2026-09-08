"""Read-only queries against the Phase 3 catalogue (Postgres).

Backs the in-cluster MCP server's catalogue tools -- the Phase 5 stretch
goal ("expose the Phase 3 catalogue over MCP so questions like 'which
running images contain this package' can be asked conversationally
against real cluster data"). Deliberately read-only: this module never
writes to the catalogue, that's the runtime-inventory/sbom-generate/
sbom-rescan jobs' job (phase3-inventory/jobs/), not the MCP server's.
"""

from __future__ import annotations

import os

import psycopg


def _dsn() -> str:
    dsn = os.environ.get("CATALOGUE_DSN")
    if not dsn:
        raise RuntimeError(
            "CATALOGUE_DSN not set. The catalogue tools only work when this "
            "server is deployed in-cluster with access to the Phase 3 "
            "Postgres catalogue -- see phase5-agentic/manifests/."
        )
    return dsn


def images_containing_package(package_name: str) -> list[dict]:
    """Which tracked images contain a given package, and at what severity."""
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT i.repository, i.tag, f.package_name, f.package_version, f.severity
            FROM findings f
            JOIN images i ON i.id = f.image_id
            JOIN scan_results sr ON sr.id = f.scan_result_id
            WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id)
            AND f.package_name ILIKE %s
            ORDER BY i.repository
            """,
            (f"%{package_name}%",),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def findings_for_image(repository: str, tag: str | None = None) -> list[dict]:
    """All current findings for a specific tracked image."""
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        query = """
            SELECT f.vulnerability_id, f.severity, f.package_name, f.package_version, f.fix_state
            FROM findings f
            JOIN images i ON i.id = f.image_id
            JOIN scan_results sr ON sr.id = f.scan_result_id
            WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id)
            AND i.repository ILIKE %s
        """
        params: list[str] = [f"%{repository}%"]
        if tag:
            query += " AND i.tag = %s"
            params.append(tag)
        query += " ORDER BY f.severity, f.vulnerability_id"
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def catalogue_summary() -> dict:
    """Aggregate counts -- images/SBOMs/packages/findings tracked right now."""
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM images) AS images_tracked,
              (SELECT count(*) FROM sboms) AS sboms_stored,
              (SELECT sum(package_count) FROM sboms) AS total_packages,
              (SELECT count(*) FROM findings f
                 JOIN scan_results sr ON sr.id = f.scan_result_id
                 WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id)
              ) AS total_findings
            """
        )
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, cur.fetchone()))
