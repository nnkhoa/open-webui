import logging
import time
from typing import Optional

from open_webui.internal.db import Base, get_db_context
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, Index, Integer, String, Text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


class AI4BISidebarSignal(Base):
    __tablename__ = 'ai4bi_sidebar_signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    connection_id = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    fingerprint = Column(String, nullable=True)
    generated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('ix_ai4bi_sidebar_signals_user_conn', 'user_id', 'connection_id'),
    )


class AI4BISidebarHeartbeat(Base):
    __tablename__ = 'ai4bi_sidebar_heartbeat'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    connection_id = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    value = Column(String, nullable=False)
    delta = Column(String, nullable=True)
    trend = Column(String, nullable=False)
    generated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('ix_ai4bi_sidebar_heartbeat_user_conn', 'user_id', 'connection_id'),
    )


class SidebarSignalRow(BaseModel):
    id: int
    rank: int
    type: str
    title: str
    desc: str
    fingerprint: Optional[str] = None
    generated_at: int

    model_config = ConfigDict(from_attributes=True)


class SidebarHeartbeatRow(BaseModel):
    id: int
    rank: int
    label: str
    value: str
    delta: Optional[str] = None
    trend: str
    generated_at: int

    model_config = ConfigDict(from_attributes=True)


class SidebarCache:
    def get_signals(
        self, user_id: str, connection_id: str, db: Optional[Session] = None
    ) -> list[SidebarSignalRow]:
        with get_db_context(db) as db:
            rows = (
                db.query(AI4BISidebarSignal)
                .filter_by(user_id=user_id, connection_id=connection_id)
                .order_by(AI4BISidebarSignal.rank.asc())
                .all()
            )
            return [
                SidebarSignalRow(
                    id=row.id,
                    rank=row.rank,
                    type=row.type,
                    title=row.title,
                    desc=row.description,
                    fingerprint=row.fingerprint,
                    generated_at=int(row.generated_at or 0),
                )
                for row in rows
            ]

    def get_heartbeat(
        self, user_id: str, connection_id: str, db: Optional[Session] = None
    ) -> list[SidebarHeartbeatRow]:
        with get_db_context(db) as db:
            rows = (
                db.query(AI4BISidebarHeartbeat)
                .filter_by(user_id=user_id, connection_id=connection_id)
                .order_by(AI4BISidebarHeartbeat.rank.asc())
                .all()
            )
            return [
                SidebarHeartbeatRow(
                    id=row.id,
                    rank=row.rank,
                    label=row.label,
                    value=row.value,
                    delta=row.delta,
                    trend=row.trend,
                    generated_at=int(row.generated_at or 0),
                )
                for row in rows
            ]

    def latest_generated_at(
        self, user_id: str, connection_id: str, db: Optional[Session] = None
    ) -> int:
        # Return the freshest generated_at across both tables for this user+connection.
        # 0 means "no cached snapshot yet".
        with get_db_context(db) as db:
            sig = (
                db.query(AI4BISidebarSignal.generated_at)
                .filter_by(user_id=user_id, connection_id=connection_id)
                .order_by(AI4BISidebarSignal.generated_at.desc())
                .first()
            )
            hb = (
                db.query(AI4BISidebarHeartbeat.generated_at)
                .filter_by(user_id=user_id, connection_id=connection_id)
                .order_by(AI4BISidebarHeartbeat.generated_at.desc())
                .first()
            )
            return max(int((sig or [0])[0] or 0), int((hb or [0])[0] or 0))

    def replace_signals(
        self,
        user_id: str,
        connection_id: str,
        items: list[dict],
        db: Optional[Session] = None,
    ) -> int:
        now = int(time.time())
        with get_db_context(db) as db:
            try:
                db.query(AI4BISidebarSignal).filter_by(
                    user_id=user_id, connection_id=connection_id
                ).delete(synchronize_session=False)
                for index, item in enumerate(items, start=1):
                    db.add(
                        AI4BISidebarSignal(
                            user_id=user_id,
                            connection_id=connection_id,
                            rank=int(item.get('rank') or index),
                            type=str(item.get('type') or 'watch'),
                            title=str(item.get('title') or ''),
                            description=str(item.get('desc') or item.get('description') or ''),
                            fingerprint=item.get('fingerprint'),
                            generated_at=now,
                        )
                    )
                db.commit()
                return len(items)
            except Exception as error:
                log.exception('Error replacing sidebar signals: %s', error)
                db.rollback()
                return 0

    def replace_heartbeat(
        self,
        user_id: str,
        connection_id: str,
        items: list[dict],
        db: Optional[Session] = None,
    ) -> int:
        now = int(time.time())
        with get_db_context(db) as db:
            try:
                db.query(AI4BISidebarHeartbeat).filter_by(
                    user_id=user_id, connection_id=connection_id
                ).delete(synchronize_session=False)
                for index, item in enumerate(items, start=1):
                    db.add(
                        AI4BISidebarHeartbeat(
                            user_id=user_id,
                            connection_id=connection_id,
                            rank=int(item.get('rank') or index),
                            label=str(item.get('label') or ''),
                            value=str(item.get('value') or ''),
                            delta=item.get('delta') or None,
                            trend=str(item.get('trend') or 'neutral'),
                            generated_at=now,
                        )
                    )
                db.commit()
                return len(items)
            except Exception as error:
                log.exception('Error replacing sidebar heartbeat: %s', error)
                db.rollback()
                return 0


sidebar_cache = SidebarCache()
