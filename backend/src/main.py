import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from src.config.database import Base,engine,replica_engine
from src.models import entities
from src.controllers.auth import router as auth
from src.routes import relations,dependencies,reports,audit
from src.middlewares.errors import ErrorMiddleware
from src.middlewares.request_id import RequestIdMiddleware
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    # 从库只读，不建表；表结构由主库复制过来。
    if os.getenv('SEED_DEMO','true')=='true':
        try:
            from scripts.seed_demo import seed
            seed()
        except Exception: logging.exception('seed failed; manual retry is available')
    yield
app=FastAPI(title='实验委托模型拆解册',lifespan=lifespan)
app.add_middleware(ErrorMiddleware);app.add_middleware(RequestIdMiddleware)
for r in (auth,relations.router,dependencies.router,reports.router,audit.router): app.include_router(r)
@app.get('/health')
def health():
    with engine.connect() as c: c.execute(text('SELECT 1'))
    from src.services.reports import queue
    queue.ping()
    # 从库只影响报告查询的读路径；它的健康不影响主流程判定。
    replica='not-configured'
    if replica_engine is not None:
        try:
            with replica_engine.connect() as c: c.execute(text('SELECT 1'))
            replica='healthy'
        except Exception: replica='unavailable'
    return {'status':'healthy','replica':replica}
