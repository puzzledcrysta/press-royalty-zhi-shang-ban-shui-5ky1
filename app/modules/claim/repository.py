from datetime import datetime, timezone
from decimal import Decimal
from app.store import connection


def _now():
    return datetime.now(timezone.utc).isoformat()


def load(run_id):
    with connection() as db:
        flow_rows = db.execute('SELECT flow_id,amount,line FROM claim_flows WHERE run_id=? ORDER BY line',
                               (run_id,)).fetchall()
        receipt_rows = db.execute(
            'SELECT flow_id,statement_key,receipt_id,amount,line,received FROM claim_receipts WHERE run_id=? ORDER BY line',
            (run_id,)).fetchall()
        writeoff_rows = db.execute(
            'SELECT flow_id,statement_key,amount,receipt_line,created FROM claim_writeoffs WHERE run_id=? ORDER BY receipt_line',
            (run_id,)).fetchall()
    flows = [{'flow_id': r['flow_id'], 'amount': Decimal(r['amount']), 'line': r['line']} for r in flow_rows]
    receipts = [{'flow_id': r['flow_id'], 'key': r['statement_key'], 'receipt_id': r['receipt_id'],
                 'amount': Decimal(r['amount']), 'line': r['line'], 'received': r['received']} for r in receipt_rows]
    writeoffs = [{'flow_id': r['flow_id'], 'key': r['statement_key'], 'amount': Decimal(r['amount']),
                  'receipt_line': r['receipt_line'], 'created': r['created']} for r in writeoff_rows]
    return flows, receipts, writeoffs


def replace_flows(run_id, flows):
    """整批替换流水；核销与回单保留，重跑时已核销归属不会丢失或重复。"""
    stamp = _now()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM claim_flows WHERE run_id=?', (run_id,))
        db.executemany('INSERT INTO claim_flows VALUES (?,?,?,?,?)',
                       [(run_id, f['flow_id'], str(f['amount']), f['line'], stamp) for f in flows])


def add_receipts(run_id, receipts):
    """登记回单。重复上传同一 (流水,结算单) 直接忽略，保证补传与重跑幂等。"""
    stamp = _now()
    stored = []
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        for receipt in receipts:
            cursor = db.execute(
                'INSERT OR IGNORE INTO claim_receipts VALUES (?,?,?,?,?,?,?)',
                (run_id, receipt['flow_id'], receipt['key'], receipt['receipt_id'],
                 str(receipt['amount']), receipt['line'], stamp))
            if cursor.rowcount:
                stored.append(receipt)
    return stored


def add_writeoffs(run_id, entries):
    """落核销记录。(run,flow,statement) 与回单行双重唯一，重跑不会重复核销。"""
    stamp = _now()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        for entry in entries:
            db.execute(
                'INSERT OR IGNORE INTO claim_writeoffs VALUES (?,?,?,?,?,?)',
                (run_id, entry['flow_id'], entry['key'], str(entry['amount']),
                 entry['receipt_line'], stamp))
