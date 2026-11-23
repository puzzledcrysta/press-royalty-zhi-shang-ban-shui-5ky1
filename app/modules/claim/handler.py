from fastapi import APIRouter
from app.inputs import ClaimFlow, ClaimReceipt
from . import service

router = APIRouter()

@router.get('/api/claim/{run_id}')
def status(run_id: str):
    return service.report(run_id)

@router.post('/api/claim/{run_id}/sync')
def sync(run_id: str, payload: ClaimFlow):
    return service.sync(run_id, payload.payload())

@router.post('/api/claim/{run_id}/receipts')
def receipts(run_id: str, payload: ClaimReceipt):
    return service.attach(run_id, payload.payload())
