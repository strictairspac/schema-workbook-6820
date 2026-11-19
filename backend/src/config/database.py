from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .settings import DATABASE_URL, DATABASE_REPLICA_URL


class Base(DeclarativeBase): pass


def _build_engine(url):
    options = {'pool_pre_ping': True, 'future': True}
    if url.startswith('mysql'):
        # 主库故障时快速失败，避免报告查询被长时间挂住。
        options['connect_args'] = {'connect_timeout': 2, 'read_timeout': 8, 'write_timeout': 8}
    return create_engine(url, **options)


engine = _build_engine(DATABASE_URL)
Session = sessionmaker(engine, expire_on_commit=False)

# 只读从库仅承接查询；写入、任务快照、审计始终走主库。
replica_engine = _build_engine(DATABASE_REPLICA_URL) if DATABASE_REPLICA_URL else None
ReplicaSession = sessionmaker(replica_engine, expire_on_commit=False) if replica_engine else None


def db_session():
    with Session() as db: yield db
