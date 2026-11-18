from sqlalchemy import select,update
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models.entities import Relation,Dependency,RenameBatch,Audit
from src.utils.serialization import record
from .common import write_lock

def listing(db):return [record(x) for x in db.scalars(select(RenameBatch).order_by(RenameBatch.id.desc()).limit(100))]
def history(db,ident):
    if not db.get(Relation,ident):raise HTTPException(404,'关系不存在')
    return [record(x) for x in db.scalars(select(RenameBatch).where(RenameBatch.relation_id==ident).order_by(RenameBatch.id.desc()))]

def batches_of(db,relation_id):
    return list(db.scalars(select(RenameBatch).where(RenameBatch.relation_id==relation_id).order_by(RenameBatch.result_version)))

def attributes_at_version(relation,batches,version):
    # 由当前属性集逆向回滚 version 之后的改名批次，重建该版本的属性名
    attrs=list(relation.attributes)
    for b in sorted((b for b in batches if b.result_version>version),key=lambda b:-b.result_version):
        back={c['new']:c['old'] for c in b.changes}
        attrs=[back.get(a,a) for a in attrs]
    return attrs

def translate_names(names,batches,from_version):
    # 沿改名批次链把旧版本属性名翻译为当前名称，依赖仍指向原来的属性
    out=list(names)
    for b in sorted((b for b in batches if b.result_version>from_version),key=lambda b:b.result_version):
        forward={c['old']:c['new'] for c in b.changes}
        out=[forward.get(n,n) for n in out]
    return out

def _fail(status,message,checks):raise HTTPException(status,{'message':message,'checks':checks})

def _replay(db,ident,key,relation=None):
    batch=db.scalar(select(RenameBatch).where(RenameBatch.relation_id==ident,RenameBatch.idempotency_key==key))
    if not batch:return None
    relation=relation or db.get(Relation,ident)
    return {'batch':record(batch),'relation':record(relation),'replayed':True}

def apply(db,ident,data,user):
    with write_lock():
        relation=db.get(Relation,ident,with_for_update=True)
        if not relation:raise HTTPException(404,'关系不存在')
        replay=_replay(db,ident,data.idempotency_key,relation)
        if replay:return replay
        items=[{'old':r.old.strip(),'new':r.new.strip()} for r in data.renames]
        mapping={i['old']:i['new'] for i in items}
        current=list(relation.attributes)
        olds=[i['old'] for i in items];news=[i['new'] for i in items]
        checks=[]
        baseline_ok=relation.attr_version==data.base_version
        checks.append({'name':'基线版本一致','passed':baseline_ok,'detail':f"基于草案版本 v{data.base_version} 提交" if baseline_ok else f"提交基于 v{data.base_version}，但草案已推进到 v{relation.attr_version}；并发改名只接受同一基线的一个方案"})
        missing=[o for o in olds if o not in current]
        checks.append({'name':'原名称存在','passed':not missing,'detail':'全部原名称都在当前草案中' if not missing else '当前草案中不存在：'+'、'.join(missing)})
        problems=[]
        if any(not i['new'] for i in items):problems.append('新名称不能为空')
        if any(i['old']==i['new'] for i in items):problems.append('存在改名前后相同的名称')
        if len(set(olds))!=len(olds):problems.append('原名称重复')
        if len(set(news))!=len(news):problems.append('新名称重复')
        checks.append({'name':'新名称有效','passed':not problems,'detail':'新名称非空、不超过40字且互不重复' if not problems else '；'.join(problems)})
        blocked=sorted({n for n in news if n in current and n not in set(olds)})
        checks.append({'name':'目标名无冲突','passed':not blocked,'detail':'目标名称空闲，或在本批次内互换' if not blocked else '目标名称被未参与本批改名的属性占用：'+'、'.join(blocked)})
        final=[mapping.get(a,a) for a in current]
        unique_ok=len(set(final))==len(final)
        checks.append({'name':'改名后属性唯一','passed':unique_ok,'detail':f'改名后仍为 {len(final)} 个唯一属性' if unique_ok else '改名后属性出现重复，整批不生效'})
        deps=list(db.scalars(select(Dependency).where(Dependency.relation_id==ident)))
        affected=sum(1 for d in deps if any(a in mapping for a in d.lhs+d.rhs))
        checks.append({'name':'依赖跟随改写','passed':True,'detail':f'{affected} 条依赖将跟随改名，仍指向原来的属性'})
        checks.append({'name':'历史报告保留原文','passed':True,'detail':'已有报告为冻结快照，属性名保持原文'})
        if not baseline_ok:
            replay=_replay(db,ident,data.idempotency_key,relation)
            if replay:return replay
            _fail(409,'基线版本冲突：并发改名只接受同一基线的一个方案，本次未生效',checks)
        if not all(c['passed'] for c in checks[:5]):_fail(422,'改名检查未通过，整批保留旧名称',checks)
        result=db.execute(update(Relation).where(Relation.id==ident,Relation.attr_version==data.base_version).values(attributes=final,attr_version=data.base_version+1).execution_options(synchronize_session=False))
        if result.rowcount!=1:
            db.rollback()
            replay=_replay(db,ident,data.idempotency_key)
            if replay:return replay
            _fail(409,'基线版本在提交时被并发修改，本次未生效',checks)
        for d in deps:
            lhs=[mapping.get(a,a) for a in d.lhs];rhs=[mapping.get(a,a) for a in d.rhs]
            if lhs!=d.lhs or rhs!=d.rhs:d.lhs,d.rhs=lhs,rhs
        batch=RenameBatch(relation_id=ident,idempotency_key=data.idempotency_key,base_version=data.base_version,result_version=data.base_version+1,changes=items,checks=checks,affected_dependencies=affected,actor=user.email)
        db.add(batch);db.add(Audit(actor=user.email,action=f"属性改名 {relation.code} v{data.base_version}→v{data.base_version+1}（{len(items)} 项，跟随改写 {affected} 条依赖）"))
        try:db.commit()
        except IntegrityError:
            db.rollback()
            replay=_replay(db,ident,data.idempotency_key)
            if replay:return replay
            raise HTTPException(409,'并发改名冲突，请刷新后重试')
        db.refresh(relation)
        return {'batch':record(batch),'relation':record(relation),'replayed':False}
