"""Migration f0bd01a18a3d phải nhận ra index uq_user_email_lower đã có trên SQLite.

SQLite không phản chiếu index theo biểu thức (lower(email)) qua SQLAlchemy inspector, nên bản
upstream tưởng chưa có và tạo lại → "index already exists" trên volume NBC từng bị 0.11.4 nâng rồi hạ.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / 'migrations'
    / 'versions'
    / 'f0bd01a18a3d_add_unique_normalized_user_email_index.py'
)


def _load_migration():
    spec = importlib.util.spec_from_file_location('mig_f0bd01a18a3d', MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _user_db(with_index: bool):
    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE "user" (id TEXT PRIMARY KEY, email TEXT)'))
        if with_index:
            conn.execute(
                sa.text('CREATE UNIQUE INDEX uq_user_email_lower ON "user" (lower(email)) WHERE email IS NOT NULL')
            )
    return engine


def test_expression_index_left_by_0_11_4_is_detected():
    mig = _load_migration()
    engine = _user_db(with_index=True)
    with engine.connect() as conn:
        # inspector của SQLAlchemy không thấy index biểu thức → bản upstream trả False
        assert mig.INDEX_NAME not in {i['name'] for i in sa.inspect(conn).get_indexes('user')}
        mig.op = SimpleNamespace(get_bind=lambda: conn)
        assert mig._index_exists() is True


def test_missing_index_is_reported_missing():
    mig = _load_migration()
    engine = _user_db(with_index=False)
    with engine.connect() as conn:
        mig.op = SimpleNamespace(get_bind=lambda: conn)
        assert mig._index_exists() is False
