import json
import os
import tempfile
import traceback
from pathlib import Path

from sqlalchemy import select

from src.config.database import Session
from src.models.entities import Report
from src.services.normalization import analyze
from src.services.reports import queue

ARTIFACTS = Path('/artifacts')
TERMINAL = ('completed', 'failed')


def persist_artifact(ident, result):
    """先原子落盘报告正文，再允许前端看到 completed。"""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    target = ARTIFACTS / f'report-{ident}.json'
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(ARTIFACTS), prefix=f'.report-{ident}-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise


def run_once(ident):
    with Session() as db:
        obj = db.get(Report, ident)
        if not obj or obj.status in TERMINAL:
            return
        obj.status = 'running'
        db.commit()
        snapshot = obj.input_snapshot
    result = analyze(snapshot['relation']['attributes'], snapshot['dependencies'])
    # 正文落盘成功之前，数据库里保持 running，查询方不会把空结果当成完成。
    persist_artifact(ident, result)
    with Session() as db:
        obj = db.get(Report, ident)
        if not obj or obj.status in TERMINAL:
            return
        obj.result = result
        obj.error = None
        obj.status = 'completed'
        db.commit()


def main():
    while True:
        Path('/tmp/worker-heartbeat').touch()
        item = queue.blpop('schemaworkbook:queue', timeout=2)
        if not item:
            continue
        ident = int(item[1])
        try:
            run_once(ident)
        except Exception as error:
            traceback.print_exc()
            with Session() as db:
                obj = db.get(Report, ident)
                if obj and obj.status not in TERMINAL:
                    obj.status = 'failed'
                    obj.error = str(error)
                    db.commit()


if __name__ == '__main__':
    main()
