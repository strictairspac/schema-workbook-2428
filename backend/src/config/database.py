from sqlalchemy import create_engine,event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .settings import DATABASE_URL
class Base(DeclarativeBase): pass
kwargs={'pool_pre_ping':True}
if DATABASE_URL.startswith('sqlite'):
    # 本地开发/测试专用：生产部署使用 MySQL
    kwargs['connect_args']={'check_same_thread':False,'timeout':30}
engine = create_engine(DATABASE_URL, **kwargs)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine,'connect')
    def _sqlite_wal(dbapi_conn,_):
        cur=dbapi_conn.cursor();cur.execute('PRAGMA journal_mode=WAL');cur.close()
Session = sessionmaker(engine, expire_on_commit=False)
def db_session():
    with Session() as db: yield db
