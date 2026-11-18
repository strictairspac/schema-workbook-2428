import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from src.config.database import Base,engine
from src.models import entities
from src.controllers.auth import router as auth
from src.routes import relations,dependencies,reports,audit,renames
from src.middlewares.errors import ErrorMiddleware
from src.middlewares.request_id import RequestIdMiddleware
def ensure_schema():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        if engine.dialect.name=='mysql':cols={row[1] for row in conn.execute(text('SHOW COLUMNS FROM relations'))}
        else:cols={row[1] for row in conn.execute(text('PRAGMA table_info(relations)'))}
        if 'attr_version' not in cols:conn.execute(text('ALTER TABLE relations ADD COLUMN attr_version INTEGER NOT NULL DEFAULT 1'))
@asynccontextmanager
async def lifespan(app):
    ensure_schema()
    if os.getenv('SEED_DEMO','true')=='true':
        try:
            from scripts.seed_demo import seed
            seed()
        except Exception: logging.exception('seed failed; manual retry is available')
    yield
app=FastAPI(title='实验委托模型拆解册',lifespan=lifespan)
app.add_middleware(ErrorMiddleware);app.add_middleware(RequestIdMiddleware)
for r in (auth,relations.router,dependencies.router,reports.router,audit.router,renames.router): app.include_router(r)
@app.get('/health')
def health():
    with engine.connect() as c: c.execute(text('SELECT 1'))
    from src.services.reports import queue
    queue.ping()
    return {'status':'healthy'}
