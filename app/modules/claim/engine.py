from decimal import Decimal, ROUND_HALF_UP
from app.modules.claim import repository

# 候选组合只在有限池内枚举；规模过大时一律要求回单凭据，不做猜测性归属。
MAX_ENUMERATE = 24
MAX_SOLUTIONS = 2

# 流水状态：WRITE_OFF 凭据核销 / CANDIDATE 唯一候选（仍缺回单）/
# PENDING 多组同额挂起，等回单 / DIFFERENCE 无匹配组合或凭据金额不符。
WRITE_OFF, CANDIDATE, PENDING, DIFFERENCE = 'WRITE_OFF', 'CANDIDATE', 'PENDING', 'DIFFERENCE'


def _cents(value):
    return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _subsets(pool, target):
    """返回至多两个和为 target 的不同子集（键元组），用于判定唯一/歧义/无解。"""
    items = sorted(pool, key=lambda item: (_cents(item[1]), item[0]))
    solutions = []

    def dive(start, remaining, chosen):
        if len(solutions) >= MAX_SOLUTIONS:
            return
        if remaining == 0:
            solutions.append(tuple(chosen))
            return
        for index in range(start, len(items)):
            key, amount = items[index]
            cents = _cents(amount)
            if cents > remaining:
                break
            chosen.append(key)
            dive(index + 1, remaining - cents, chosen)
            chosen.pop()

    dive(0, _cents(target), [])
    return solutions


def build(run_id, statements):
    """按已持久化的流水/回单/核销重算认领状态。纯读，不产生任何写入。"""
    flows, receipts, writeoffs = repository.load(run_id)
    payable = dict(statements)

    claimed_keys = {w['key'] for w in writeoffs}
    receipt_id_map = {(r['flow_id'], r['key']): r['receipt_id'] for r in receipts}
    result_flows = []
    candidate_hits = {}

    for flow in flows:
        evidenced = [w for w in writeoffs if w['flow_id'] == flow['flow_id']]
        if evidenced:
            matched_total = sum((w['amount'] for w in evidenced), Decimal(0))
            delta = flow['amount'] - matched_total
            result_flows.append({
                'flow_id': flow['flow_id'], 'amount': str(flow['amount']), 'line': flow['line'],
                'status': WRITE_OFF if delta == 0 else DIFFERENCE,
                'delta': str(delta), 'evidenced': True,
                'matched': [{'key': w['key'], 'amount': str(w['amount']), 'receipt_line': w['receipt_line'],
                             'receipt_id': receipt_id_map.get((w['flow_id'], w['key']))}
                            for w in evidenced], 'candidates': [],
            })
            continue

        # 无凭据流水：已被其他流水凭据核销的结算单不得再抵本流水。
        pool = [(key, amount) for key, amount in payable.items()
                if key not in claimed_keys and amount > 0]
        if len(pool) > MAX_ENUMERATE:
            status, solutions = PENDING, []
        else:
            solutions = _subsets(pool, flow['amount'])
            status = (CANDIDATE if len(solutions) == 1 else
                      PENDING if len(solutions) > 1 else DIFFERENCE)
        groups = [list(group) for group in solutions]
        for group in groups:
            for key in group:
                candidate_hits.setdefault(key, set()).add(flow['flow_id'])
        result_flows.append({
            'flow_id': flow['flow_id'], 'amount': str(flow['amount']), 'line': flow['line'],
            'status': status, 'delta': str(Decimal(0) if status == CANDIDATE else flow['amount']),
            'evidenced': False, 'matched': [], 'candidates': groups,
        })

    result_statements = []
    for key in sorted(payable):
        owner = next((w['flow_id'] for w in writeoffs if w['key'] == key), None)
        if owner:
            status, flow_id = WRITE_OFF, owner
        elif key in candidate_hits:
            status, flow_id = CANDIDATE, sorted(candidate_hits[key])
        else:
            status, flow_id = PENDING, None
        result_statements.append({'key': key, 'amount': str(payable[key]),
                                  'status': status, 'flow_id': flow_id})

    count = lambda code: sum(1 for f in result_flows if f['status'] == code)
    ready = not flows or all(f['status'] == WRITE_OFF for f in result_flows)
    blocker = None if ready else ('CLAIM_PENDING' if flows else None)
    return {
        'flows': sorted(result_flows, key=lambda f: f['line']),
        'statements': result_statements,
        'writeoffs': [{'flow_id': w['flow_id'], 'key': w['key'], 'amount': str(w['amount']),
                       'receipt_line': w['receipt_line'], 'created': w['created']} for w in writeoffs],
        'receipts': [{'receipt_id': r['receipt_id'], 'flow_id': r['flow_id'], 'key': r['key'],
                      'amount': str(r['amount']), 'line': r['line'], 'received': r['received']}
                     for r in receipts],
        'counts': {'flows': len(flows), 'write_off': count(WRITE_OFF), 'candidate': count(CANDIDATE),
                   'pending': count(PENDING), 'difference': count(DIFFERENCE),
                   'statements': len(payable), 'claimed': len(claimed_keys)},
        'ready': ready, 'blocker': blocker,
    }
