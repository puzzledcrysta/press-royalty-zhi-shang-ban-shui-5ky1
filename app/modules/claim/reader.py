from app.errors import DataError
from app.settings import UNIT, FLOW_ID, RECEIPT, CLAIM_STATEMENT
from app.modules.domain.values import number
from app.modules.intake.reader import decode, records

FLOW_HEADER = [FLOW_ID, f'扣款金额({UNIT})']
RECEIPT_HEADER = [RECEIPT, FLOW_ID, CLAIM_STATEMENT, f'回单金额({UNIT})']


def _rows(payload, expected, width_code, header_code, header_detail):
    text, _ = decode(payload)
    if not text.strip():
        raise DataError('EMPTY', '文件无内容')
    rows = iter(records(text))
    _, header = next(rows, (0, []))
    if header != expected:
        raise DataError(header_code, header_detail)
    parsed = []
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != len(expected):
            raise DataError(width_code, f'第 {line} 行列数应为 {len(expected)} 列')
        parsed.append((line, [value.strip() for value in row]))
    if not parsed:
        raise DataError('HEADER_ONLY', '文件只有表头')
    return parsed


def flows(payload):
    """银行扣款流水：流水号 + 扣款金额（一笔流水可合并多张结算单）。"""
    out, seen = [], set()
    for line, row in _rows(payload, FLOW_HEADER, 'FLOW_WIDTH', 'FLOW_HEADER', '扣款流水表头应为 扣款流水号,扣款金额(元)'):
        flow_id, amount_text = row
        if not flow_id:
            raise DataError('FLOW_WIDTH', f'第 {line} 行缺少扣款流水号')
        if flow_id in seen:
            raise DataError('FLOW_CONFLICT', f'扣款流水号 {flow_id} 重复出现')
        seen.add(flow_id)
        amount = number(amount_text)
        if amount <= 0:
            raise DataError('RANGE', f'第 {line} 行扣款金额必须为正')
        out.append({'flow_id': flow_id, 'amount': amount, 'line': line})
    return out


def receipts(payload):
    """银行回单：回单号 + 所属扣款流水 + 归属结算单 + 该单回单金额。回单是唯一凭据。"""
    out, seen = [], set()
    for line, row in _rows(payload, RECEIPT_HEADER, 'RECEIPT_WIDTH', 'RECEIPT_HEADER',
                           '银行回单表头应为 银行回单号,扣款流水号,结算单号,回单金额(元)'):
        receipt_id, flow_id, key, amount_text = row
        if not receipt_id or not flow_id or not key:
            raise DataError('RECEIPT_WIDTH', f'第 {line} 行回单号、流水号或结算单号缺失')
        identity = (flow_id, key)
        if identity in seen:
            raise DataError('RECEIPT_DUP', f'第 {line} 行回单对同一流水与结算单重复登记')
        seen.add(identity)
        amount = number(amount_text)
        if amount == 0:
            raise DataError('RANGE', f'第 {line} 行回单金额不能为零')
        out.append({'receipt_id': receipt_id, 'flow_id': flow_id, 'key': key,
                    'amount': amount, 'line': line})
    return out
