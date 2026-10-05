from __future__ import annotations

from dataclasses import dataclass

from ..db import catalog_sql


@dataclass(frozen=True)
class Domain:
    domain_id: int
    code: str
    name: str
    description: str | None


def active_domains(catalog_conn) -> list[Domain]:
    rows = catalog_sql.query(
        catalog_conn,
        "SELECT domain_id, code, name, description FROM ctl_domain WHERE status = 'active' ORDER BY domain_id",
    )
    return [Domain(**row) for row in rows]
