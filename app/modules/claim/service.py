import json
from decimal import Decimal
from app.errors import DataError
from app.store import connection
from app.modules.runs.repository import lookup
from app.modules.claim import repository
from app.modules.claim.engine import build, WRITE_OFF
from app.modules.claim.reader import flows as parse_flows, receipts as parse_receipts


def _run(run_id):
    with connection() as db:
        return json.loads(lookup(db, run_id)['result'])


def _statements(run):
    return {row['key']: Decimal(row['amount']) for row in run['accepted']}


def _validate(run_id, receipts):
    known_flows, _, writeoffs = repository.load(run_id)
    flow_ids = {f['flow_id'] for f in known_flows}
    payable = _statements(_run(run_id))
    used = {w['key']: w['flow_id'] for w in writeoffs}
    seen_keys = {}
    for receipt in receipts:
        if receipt['flow_id'] not in flow_ids:
            raise DataError('RECEIPT_FLOW', f'回单第 {receipt["line"]} 行指向未知扣款流水 {receipt["flow_id"]}')
        if receipt['key'] not in payable:
            raise DataError('RECEIPT_STATEMENT', f'回单第 {receipt["line"]} 行指向未知结算单 {receipt["key"]}')
        if receipt['amount'] != payable[receipt['key']]:
            raise DataError('RECEIPT_AMOUNT',
                            f'回单第 {receipt["line"]} 行金额 {receipt["amount"]} 与结算单 {receipt["key"]} 应付 {payable[receipt["key"]]} 不符')
        owner = used.get(receipt['key'])
        if owner is not None and owner != receipt['flow_id']:
            raise DataError('RECEIPT_USED',
                            f'结算单 {receipt["key"]} 已由扣款 {owner} 核销，不能再抵 {receipt["flow_id"]}')
        # 同一批回单内，一张结算单只能归给一笔扣款，防止同额两单串账。
        prior = seen_keys.get(receipt['key'])
        if prior is not None and prior != receipt['flow_id']:
            raise DataError('RECEIPT_USED',
                            f'回单第 {receipt["line"]} 行把已归属的结算单 {receipt["key"]} 又指给 {receipt["flow_id"]}')
        seen_keys[receipt['key']] = receipt['flow_id']


def report(run_id):
    return build(run_id, _statements(_run(run_id)))


def _materialize(run_id):
    """回单即凭据：每条已登记回单对应一条核销，靠唯一约束幂等补登。"""
    _, receipts, _ = repository.load(run_id)
    if receipts:
        repository.add_writeoffs(run_id, [
            {'flow_id': r['flow_id'], 'key': r['key'], 'amount': r['amount'],
             'receipt_line': r['line']} for r in receipts])


def sync(run_id, flow_payload):
    """用扣款流水与结算单对账。整批替换流水，已落的核销与回单保留，重跑不重复核销。"""
    run = _run(run_id)
    parsed = parse_flows(flow_payload)
    repository.replace_flows(run_id, parsed)
    _materialize(run_id)
    return build(run_id, _statements(run))


def attach(run_id, receipt_payload):
    """补银行回单：逐条凭据校验后登记并重算。校验不过整批拒绝，不产生半截归属。"""
    parsed = parse_receipts(receipt_payload)
    _validate(run_id, parsed)
    repository.add_receipts(run_id, parsed)
    _materialize(run_id)
    return build(run_id, _statements(_run(run_id)))


def assert_countersignable(run_id):
    """会签只认有凭据的归属：存在无回单流水或差异时拦截确认。"""
    state = report(run_id)
    if state['flows'] and not state['ready']:
        pending = [f['flow_id'] for f in state['flows'] if f['status'] != WRITE_OFF]
        raise DataError('CLAIM_PENDING', f'扣款 {", ".join(pending)} 尚无凭据归属，补齐回单后再会签')
