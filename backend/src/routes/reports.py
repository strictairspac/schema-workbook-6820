from fastapi import APIRouter, Depends
from fastapi.responses import Response
import json

from src.config.database import Session, ReplicaSession, db_session
from src.utils.security import current, writer
from src.schemas.report import ReportInput
from src.services import reports as service
from src.services.read_sessions import read_session

router = APIRouter()

SOURCE_LABELS = {'primary': '主库', 'replica': '从库', 'mixed': '从库 + 主库补齐'}


def report_readers(state=Depends(read_session)):
    """报告查询读取器：主库会话负责补齐/核实，读会话优先使用只读从库。"""
    replica = ReplicaSession is not None
    with Session() as primary, (ReplicaSession() if replica else Session()) as reader:
        yield primary, reader, replica, state


@router.get('/reports')
def listing(readers=Depends(report_readers), user=Depends(current)):
    primary, reader, replica, state = readers
    items, source = service.listing(reader, primary, state, reader_is_replica=replica)
    return {'items': items, 'read_source': source, 'read_source_label': SOURCE_LABELS[source]}


@router.post('/reports', status_code=201)
def create(data: ReportInput, db=Depends(db_session), user=Depends(writer), state=Depends(read_session)):
    body = service.create(db, data, user, state)
    return {**body, 'read_source': 'primary', 'read_source_label': SOURCE_LABELS['primary']}


@router.get('/reports/{ident}')
def detail(ident: int, readers=Depends(report_readers), user=Depends(current)):
    primary, reader, replica, state = readers
    row, source = service.detail(reader, primary, state, ident, reader_is_replica=replica)
    return {'report': row, 'read_source': source, 'read_source_label': SOURCE_LABELS[source]}


@router.get('/reports/{ident}/export')
def export(ident: int, readers=Depends(report_readers), user=Depends(current)):
    primary, reader, replica, state = readers
    row, source = service.detail(reader, primary, state, ident, reader_is_replica=replica)
    payload = {**row, 'read_source': source, 'read_source_label': SOURCE_LABELS[source]}
    return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="report-{ident}.json"'})
