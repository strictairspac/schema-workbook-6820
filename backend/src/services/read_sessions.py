"""按阅读会话记录进度下界，保证复制延迟下读到的状态不倒退。

每个浏览器标签页生成稳定的阅读会话标识（X-Read-Session），后端据此记住：
- 本会话受理过的任务编号；
- 本会话读到过的每条报告状态（单调前进）。

复制延迟或并发刷新返回乱序时，用这份进度下界校验从库结果；主库不可用时，
只有从库已经追上本会话进度的查询才继续返回，否则明确提示暂不可用。
"""
import hashlib
import threading
import time

from fastapi import Depends, Header
from fastapi.security import HTTPBearer

bearer = HTTPBearer(auto_error=False)

STATUS_RANK = {'queued': 0, 'running': 1, 'completed': 2, 'failed': 2}
MAX_READ_SESSIONS = 4096
SESSION_TTL = 6 * 60 * 60


def rank(status):
    return STATUS_RANK.get(status, 0)


class ReadSession:
    __slots__ = ('key', 'accepted', 'statuses', 'touched')

    def __init__(self, key):
        self.key = key
        self.accepted = set()
        self.statuses = {}
        self.touched = time.time()

    def accepted_ids(self):
        return set(self.accepted)

    def known_statuses(self):
        return dict(self.statuses)


_lock = threading.Lock()
_sessions = {}


def _prune(now):
    if len(_sessions) < MAX_READ_SESSIONS:
        return
    for key, state in list(_sessions.items()):
        if now - state.touched > SESSION_TTL:
            _sessions.pop(key, None)
    overflow = len(_sessions) - MAX_READ_SESSIONS + 1
    if overflow > 0:
        for key, _ in sorted(_sessions.items(), key=lambda kv: kv[1].touched)[:overflow]:
            _sessions.pop(key, None)


def get_session(key):
    now = time.time()
    with _lock:
        _prune(now)
        state = _sessions.get(key)
        if state is None:
            state = ReadSession(key)
            _sessions[key] = state
        state.touched = now
        return state


def session_key(client_id, token):
    """优先按标签页标识区分会话；客户端未提供时退化为访问令牌。"""
    if client_id and client_id.strip():
        return 'client:' + hashlib.sha256(client_id.strip().encode()).hexdigest()[:24]
    if token:
        return 'token:' + hashlib.sha256(token.encode()).hexdigest()[:24]
    return 'anonymous'


def read_session(
    x_read_session: str | None = Header(default=None, alias='X-Read-Session'),
    credentials=Depends(bearer),
):
    token = credentials.credentials if credentials else None
    return get_session(session_key(x_read_session, token))


def note_accepted(state, ident):
    """登记本会话刚受理的任务，复制尚未追上时由主库补齐。"""
    with _lock:
        state.accepted.add(int(ident))
        state.touched = time.time()


def merge_status(previous, incoming):
    """状态只前进；两个终态冲突时保留先读到的终态。"""
    if previous is None:
        return incoming
    if rank(incoming) < rank(previous):
        return previous
    if rank(incoming) == rank(previous) == 2 and incoming != previous:
        return previous
    return incoming


def observe(state, rows):
    """把本次返回的行并入会话进度下界。"""
    now = time.time()
    with _lock:
        for row in rows:
            ident = int(row['id'])
            state.statuses[ident] = merge_status(state.statuses.get(ident), row['status'])
        state.touched = now


def floor(state):
    """读取当前会话的进度下界（受理集合与已读状态）。"""
    with _lock:
        return set(state.accepted), dict(state.statuses)
