import threading
from contextlib import nullcontext
from src.models.entities import Audit
from src.utils.serialization import record
from src.config.database import engine
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
def save(db,obj,user,action):
    db.add(obj);db.add(Audit(actor=user.email,action=action))
    try: db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'编号已存在或引用对象无效，请调整后重试')
    return record(obj)
_sqlite_lock=threading.RLock()
def write_lock():
    # MySQL 下关键区由 SELECT ... FOR UPDATE 行锁串行化；SQLite 仅用于本地开发/测试，无行锁，用进程锁模拟同一语义
    return _sqlite_lock if engine.dialect.name=='sqlite' else nullcontext()
