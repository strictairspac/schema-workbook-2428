from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.relation import RenameInput
from src.services import renames as service
router=APIRouter()
@router.get('/renames')
def listing(db=Depends(db_session),user=Depends(current)):return service.listing(db)
@router.get('/relations/{ident}/renames')
def history(ident:int,db=Depends(db_session),user=Depends(current)):return service.history(db,ident)
@router.post('/relations/{ident}/renames')
def apply(ident:int,data:RenameInput,db=Depends(db_session),user=Depends(writer)):return service.apply(db,ident,data,user)
