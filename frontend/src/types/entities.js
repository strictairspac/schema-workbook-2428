/** Relation:{id,code,title,attributes,attr_version,note}; Dependency:{id,relation_id,lhs,rhs,note}; Report:{id,name,relation_id,input_snapshot,status,result,error}; RenameBatch:{id,relation_id,idempotency_key,base_version,result_version,changes,checks,affected_dependencies,actor,created_at} */
export const entityNames=['relations','dependencies','reports','renames'];
