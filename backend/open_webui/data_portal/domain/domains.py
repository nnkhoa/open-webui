from __future__ import annotations

from ..db import catalog_sql


def domain_forms(catalog_conn, domain_id: int) -> list[dict]:
    return catalog_sql.query(
        catalog_conn,
        'SELECT f.form_id, f.code FROM ctl_domain_form df '
        '  JOIN ctl_form f ON f.form_id = df.form_id '
        ' WHERE df.domain_id = ? ORDER BY df.position, f.form_id',
        (domain_id,),
    )
