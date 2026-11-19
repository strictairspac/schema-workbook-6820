"""分解报告查询读写分离。

写入、快照冻结、入队与审计只走主库；列表与详情查询默认走只读从库，并叠加
按阅读会话维护的进度下界：

1. 刚受理的任务：受理时登记编号，从库未复制到也由主库补齐，保证查得到；
2. 不倒退：会话已读到的状态只能前进，复制延迟或并发乱序不会把完成刷回排队；
3. 主库中断：从库已追上本会话进度的会话继续可查；有任一缺口就明确提示暂不可用，
   而不是拿从库旧值冒充，也不把任务误报成不存在；
4. 正文落盘后才显示完成：completed 必须同时带着 result；缺失时向主库核实。
"""
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException

from src.models.entities import Relation, Dependency, Report
from src.utils.serialization import record
from .common import save
from ._queue import queue
from .read_sessions import floor, merge_status, note_accepted, observe, rank

PRIMARY = 'primary'
REPLICA = 'replica'
MIXED = 'mixed'

UNAVAILABLE = '主库暂时不可用，且本会话的报告进度尚未复制到从库，请稍后重试'
SYNCING = '报告状态同步中，请稍后重试'


def has_body(row):
    """completed 必须带着落盘正文；缺正文的完成态视为尚未可见。"""
    return row is not None and (row['status'] != 'completed' or row.get('result') is not None)


def _all(db):
    return [record(x) for x in db.scalars(select(Report).order_by(Report.id.desc()))]


def _one(db, ident):
    obj = db.get(Report, ident)
    return record(obj) if obj else None


def _merge(local, fresh):
    """以会话已读进度为准合并：状态只前进，已有正文不丢。"""
    if local is None:
        return dict(fresh)
    status = merge_status(local['status'], fresh['status'])
    merged = dict(fresh) if rank(fresh['status']) >= rank(local['status']) else dict(local)
    merged['status'] = status
    if status == 'completed':
        if merged.get('result') is None:
            merged['result'] = local.get('result')
        if merged.get('error') is None:
            merged['error'] = local.get('error')
    return merged


def _apply_floor(by_id, known):
    """把会话已读状态并到返回行上：同一会话看到的进度只前进。"""
    for ident, status in known.items():
        row = by_id.get(ident)
        if row is not None:
            settled = merge_status(row['status'], status)
            if settled != row['status']:
                by_id[ident] = dict(row, status=settled)


def _gaps(by_id, accepted, known):
    """相对会话进度下界的缺口：缺的已受理任务、被刷旧的状态、缺正文的完成。"""
    gaps = set()
    for ident in accepted:
        if ident not in by_id:
            gaps.add(ident)
    for ident, status in known.items():
        row = by_id.get(ident)
        if row is None or rank(row['status']) < rank(status):
            # 本会话读到过的报告不能因复制延迟而消失或被刷旧。
            gaps.add(ident)
    for ident, row in by_id.items():
        if not has_body(row):
            gaps.add(ident)
    return gaps


def _from_primary(primary, idents):
    if not idents:
        return []
    try:
        return [record(x) for x in primary.scalars(select(Report).where(Report.id.in_(sorted(idents))))]
    except OperationalError:
        primary.rollback()
        raise HTTPException(503, UNAVAILABLE)


def _read_all(reader, primary, reader_is_replica):
    """从库不可用时回退主库读取；返回结果与实际读取来源。"""
    try:
        return _all(reader), (REPLICA if reader_is_replica else PRIMARY)
    except OperationalError:
        reader.rollback()
        if not reader_is_replica:
            raise HTTPException(503, '数据库暂时不可用，请稍后重试')
    try:
        return _all(primary), PRIMARY
    except OperationalError:
        primary.rollback()
        raise HTTPException(503, UNAVAILABLE)


def listing(reader, primary, state, reader_is_replica=True):
    rows, source = _read_all(reader, primary, reader_is_replica)
    by_id = {row['id']: row for row in rows}
    accepted, known = floor(state)

    gaps = _gaps(by_id, accepted, known)
    if gaps:
        if source == PRIMARY:
            # 已直读主库仍缺，说明写入尚未可见，不拿旧值冒充。
            raise HTTPException(503, SYNCING)
        for row in _from_primary(primary, gaps):
            by_id[row['id']] = _merge(by_id.get(row['id']), row)
        if _gaps(by_id, accepted, known):
            raise HTTPException(503, SYNCING)
        source = MIXED

    _apply_floor(by_id, known)
    merged = sorted(by_id.values(), key=lambda row: row['id'], reverse=True)
    observe(state, merged)
    return merged, source


def detail(reader, primary, state, ident, reader_is_replica=True):
    accepted, known = floor(state)
    try:
        row = _one(reader, ident)
        source = REPLICA if reader_is_replica else PRIMARY
    except OperationalError:
        reader.rollback()
        if not reader_is_replica:
            raise HTTPException(503, '数据库暂时不可用，请稍后重试')
        row, source = None, REPLICA

    known_status = known.get(ident)
    # 本会话已读到的进度与从库不一致（被刷旧、终态冲突或整行消失）都属缺口。
    behind = row is not None and known_status is not None and merge_status(row['status'], known_status) != row['status']
    vanished = row is None and known_status is not None
    if row is None or behind or vanished or not has_body(row):
        fresh = _from_primary(primary, [ident])
        fresh = fresh[0] if fresh else None
        if fresh is None:
            if ident in accepted or ident in known:
                # 本会话受理/读到过，主库却不可达或尚无此行：不误报不存在。
                raise HTTPException(503, UNAVAILABLE)
            raise HTTPException(404, '报告不存在')
        row = _merge(None if vanished else row, fresh)
        if source == REPLICA:
            source = MIXED

    if row is not None and known_status is not None:
        # 终态冲突时保留本会话先读到的终态。
        settled = merge_status(row['status'], known_status)
        if settled != row['status']:
            row = dict(row, status=settled)

    if not has_body(row) or rank(row['status']) < rank(known_status):
        raise HTTPException(503, SYNCING)

    observe(state, [row])
    return row, source


def create(db, data, user, state=None):
    relation = db.get(Relation, data.relation_id)
    if not relation:
        raise HTTPException(404, '关系不存在')
    deps = list(db.scalars(select(Dependency).where(Dependency.relation_id == relation.id)))
    input_snapshot = {'relation': record(relation), 'dependencies': [{'lhs': x.lhs, 'rhs': x.rhs} for x in deps]}
    obj = Report(**data.model_dump(), input_snapshot=input_snapshot, status='queued')
    result = save(db, obj, user, '范式分解入队 ' + data.name)
    if state is not None:
        note_accepted(state, obj.id)
    try:
        queue.rpush('schemaworkbook:queue', str(obj.id))
    except Exception:
        obj.status = 'failed'; obj.error = '队列暂时不可用，请重新创建'; db.commit()
        raise HTTPException(503, obj.error)
    return result
