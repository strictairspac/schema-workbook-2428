from sqlalchemy import select,func
from fastapi import HTTPException
from src.models.entities import Relation,Dependency
from src.utils.serialization import record
from .common import save,write_lock
from .renames import batches_of,attributes_at_version,translate_names
def listing(db):return [record(x) for x in db.scalars(select(Dependency).order_by(Dependency.id))]
def _resolve(db,relation,names,attr_version):
    # 携带版本：按原版本校验并沿改名链翻译；缺少版本：仅接受无歧义名称
    current=relation.attr_version
    if attr_version is not None:
        if attr_version>current:raise HTTPException(409,f'依赖基于草案版本 v{attr_version}，高于当前 v{current}，请刷新后重试')
        if attr_version<current:
            batches=batches_of(db,relation.id)
            known=attributes_at_version(relation,batches,attr_version)
            missing=sorted({n for n in names if n not in known})
            if missing:raise HTTPException(422,f"属性 {'、'.join(missing)} 在草案版本 v{attr_version} 中不存在，请刷新后重试")
            return translate_names(names,batches,attr_version)
        return list(names)
    batches=batches_of(db,relation.id)
    current_attrs=set(relation.attributes)
    renamed_away={c['old'] for b in batches for c in b.changes}
    introduced={c['new'] for b in batches for c in b.changes}
    ambiguous=sorted({n for n in names if (n in current_attrs and n in renamed_away) or (n not in current_attrs and (n in renamed_away or n in introduced))})
    if ambiguous:raise HTTPException(409,f"属性名 {'、'.join(ambiguous)} 经历过改名，缺少草案版本无法确认指向，为避免把规则写给另一属性请刷新页面后重试")
    return list(names)
def _validate(db,data,exclude=None):
    relation=db.get(Relation,data.relation_id,with_for_update=True)
    if not relation:raise HTTPException(404,'关系不存在')
    lhs=_resolve(db,relation,data.lhs,data.attr_version)
    rhs=_resolve(db,relation,data.rhs,data.attr_version)
    if not set(lhs+rhs)<=set(relation.attributes):raise HTTPException(422,'依赖属性必须属于选定关系')
    count=db.scalar(select(func.count()).select_from(Dependency).where(Dependency.relation_id==data.relation_id))
    if not exclude and count>=64:raise HTTPException(422,'最多64条函数依赖，请合并后重试')
    return lhs,rhs
def create(db,data,user):
    with write_lock():
        lhs,rhs=_validate(db,data)
        payload=data.model_dump(exclude={'attr_version'});payload['lhs']=lhs;payload['rhs']=rhs
        return save(db,Dependency(**payload),user,'创建函数依赖')
def update(db,ident,data,user):
    with write_lock():
        obj=db.get(Dependency,ident)
        if not obj:raise HTTPException(404,'依赖不存在')
        lhs,rhs=_validate(db,data,ident)
        payload=data.model_dump(exclude={'attr_version'});payload['lhs']=lhs;payload['rhs']=rhs
        for k,v in payload.items():setattr(obj,k,v)
        return save(db,obj,user,'更新函数依赖')
