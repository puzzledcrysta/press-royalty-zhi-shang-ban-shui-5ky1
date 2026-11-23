import pytest
from app.errors import DataError

FLOW_HEADER = '扣款流水号,扣款金额(元)\n'
RECEIPT_HEADER = '银行回单号,扣款流水号,结算单号,回单金额(元)\n'


@pytest.fixture
def anchor(client):
    return client.post('/api/runs', json={}).json()['manifest']['run_id']


def sync(client, anchor, *rows):
    return client.post(f'/api/claim/{anchor}/sync',
                       json={'flows': FLOW_HEADER + ''.join(f'{a},{b}\n' for a, b in rows)})


def attach(client, anchor, *rows):
    return client.post(f'/api/claim/{anchor}/receipts',
                       json={'receipts': RECEIPT_HEADER + ''.join(','.join(map(str, r)) + '\n' for r in rows)})


def test_empty_report_before_sync(client, anchor):
    state = client.get(f'/api/claim/{anchor}').json()
    assert state['flows'] == [] and state['ready'] is True and state['counts']['flows'] == 0


def test_equal_amount_groups_stay_pending(client, anchor):
    # BK-01 与 BK-02 同额 234.00：存在多组等额组合，自动归属必须全部挂起，不许先认领。
    response = sync(client, anchor, ('BK-01', '234.00'), ('BK-02', '234.00'), ('BK-03', '77.00'))
    assert response.status_code == 200
    state = response.json()
    assert {f['flow_id']: f['status'] for f in state['flows']} == {
        'BK-01': 'PENDING', 'BK-02': 'PENDING', 'BK-03': 'DIFFERENCE'}
    assert state['ready'] is False and state['blocker'] == 'CLAIM_PENDING'
    # 挂起流水都带有多组候选，提示需要回单凭据。
    for flow in state['flows']:
        if flow['status'] == 'PENDING':
            assert len(flow['candidates']) >= 2


def test_unique_subset_is_candidate_but_not_writeoff(client, anchor):
    state = sync(client, anchor, ('BK-A', '50.54')).json()
    flow = state['flows'][0]
    assert flow['status'] == 'CANDIDATE' and flow['candidates'] == [['00106']]
    assert flow['matched'] == [] and state['counts']['write_off'] == 0
    # 金额对外一律字符串传输，与复算结果的约定一致。
    assert isinstance(flow['delta'], str) and isinstance(flow['amount'], str)


def test_receipt_only_writeoff_and_gate(client, anchor):
    sync(client, anchor, ('BK-A', '50.54'))
    # 无凭据的候选态不能会签确认。
    blocked = client.post(f'/api/review/{anchor}', json={'version': 0, 'decision': '确认', 'note': '待回单'})
    assert blocked.status_code == 422 and blocked.json()['code'] == 'CLAIM_PENDING'

    state = attach(client, anchor, ('R1', 'BK-A', '00106', '50.54')).json()
    flow = state['flows'][0]
    assert flow['status'] == 'WRITE_OFF' and flow['evidenced'] is True
    assert flow['matched'] == [{'key': '00106', 'amount': '50.54', 'receipt_line': 2, 'receipt_id': 'R1'}]
    assert state['ready'] is True
    # 补齐凭据后会签确认放行。
    ok = client.post(f'/api/review/{anchor}', json={'version': 0, 'decision': '确认', 'note': '回单已核'})
    assert ok.status_code == 200 and ok.json()['decision'] == '确认'


def test_rerun_keeps_writeoffs_and_never_duplicates(client, anchor):
    sync(client, anchor, ('BK-01', '234.00'), ('BK-02', '234.00'), ('BK-03', '77.00'))
    first = attach(client, anchor,
                   ('RB-1001', 'BK-01', '00101', '144.00'), ('RB-1002', 'BK-01', '00102', '90.00')).json()
    assert first['counts']['write_off'] == 1 and len(first['writeoffs']) == 2

    # 重新上传同一批流水：核销与回单保留。
    rerun = sync(client, anchor, ('BK-01', '234.00'), ('BK-02', '234.00'), ('BK-03', '77.00')).json()
    assert len(rerun['writeoffs']) == 2 and rerun['counts']['write_off'] == 1
    # 重复补同一回单：幂等，不产生重复核销。
    again = attach(client, anchor,
                   ('RB-1001', 'BK-01', '00101', '144.00'), ('RB-1002', 'BK-01', '00102', '90.00')).json()
    assert len(again['writeoffs']) == 2 and len(again['receipts']) == 2


def test_written_off_statement_cannot_offset_another_flow(client, anchor):
    sync(client, anchor, ('BK-X', '144.00'), ('BK-Y', '144.00'))
    attach(client, anchor, ('RX', 'BK-X', '00101', '144.00'))
    # 已核销给 BK-X 的 00101 不能再抵 BK-Y，即便金额恰好相等。
    stolen = attach(client, anchor, ('RY1', 'BK-Y', '00101', '144.00'))
    assert stolen.status_code == 422 and stolen.json()['code'] == 'RECEIPT_USED'
    # 另一张同额结算单仍可凭回单归属 BK-Y。
    ok = attach(client, anchor, ('RY2', 'BK-Y', '00107', '144.00'))
    assert ok.status_code == 200 and ok.json()['ready'] is True


def test_partial_receipt_marks_difference(client, anchor):
    sync(client, anchor, ('BK-02', '234.00'))
    state = attach(client, anchor,
                   ('RB-1003', 'BK-02', '00103', '90.90'), ('RB-1004', 'BK-02', '00109', '93.90')).json()
    flow = state['flows'][0]
    assert flow['status'] == 'DIFFERENCE' and flow['delta'] == '49.20'
    assert state['ready'] is False


def test_receipt_validation_rejects_bad_evidence(client, anchor):
    sync(client, anchor, ('BK-A', '50.54'))
    cases = [
        (('R', 'BK-Z', '00106', '50.54'), 'RECEIPT_FLOW'),
        (('R', 'BK-A', '99999', '1.00'), 'RECEIPT_STATEMENT'),
        (('R', 'BK-A', '00106', '50.00'), 'RECEIPT_AMOUNT'),
    ]
    for row, code in cases:
        response = attach(client, anchor, row)
        assert response.status_code == 422 and response.json()['code'] == code
    # 整批校验失败不产生任何核销。
    assert client.get(f'/api/claim/{anchor}').json()['writeoffs'] == []


def test_flow_file_guards(client, anchor):
    bad_header = client.post(f'/api/claim/{anchor}/sync', json={'flows': 'x,y\nBK-A,1\n'})
    assert bad_header.status_code == 422 and bad_header.json()['code'] == 'FLOW_HEADER'
    duplicate = client.post(f'/api/claim/{anchor}/sync',
                            json={'flows': FLOW_HEADER + 'BK-A,1\nBK-A,2\n'})
    assert duplicate.json()['code'] == 'FLOW_CONFLICT'
    non_positive = client.post(f'/api/claim/{anchor}/sync',
                               json={'flows': FLOW_HEADER + 'BK-A,0\n'})
    assert non_positive.json()['code'] == 'RANGE'


def test_claim_state_unknown_run_is_404(client):
    assert client.get('/api/claim/missing').status_code == 404
    assert client.post('/api/claim/missing/sync', json={'flows': FLOW_HEADER}).status_code == 404


def test_statement_table_reflects_ownership(client, anchor):
    sync(client, anchor, ('BK-A', '50.54'))
    before = {s['key']: s for s in client.get(f'/api/claim/{anchor}').json()['statements']}
    assert before['00106']['status'] == 'CANDIDATE' and before['00106']['flow_id'] == ['BK-A']
    attach(client, anchor, ('R1', 'BK-A', '00106', '50.54'))
    after = {s['key']: s for s in client.get(f'/api/claim/{anchor}').json()['statements']}
    assert after['00106']['status'] == 'WRITE_OFF' and after['00106']['flow_id'] == 'BK-A'
    assert after['00101']['status'] == 'PENDING' and after['00101']['flow_id'] is None


def test_receipt_sample_endpoint(client):
    response = client.get('/api/samples/receipts')
    assert response.status_code == 200 and response.content.startswith('银行回单号'.encode())
    flows = client.get('/api/samples/flows')
    assert flows.status_code == 200 and b'BK-01' in flows.content


def test_concurrent_receipt_uploads_write_once(client, anchor):
    from concurrent.futures import ThreadPoolExecutor
    from app.modules.claim import service
    sync(client, anchor, ('BK-A', '50.54'))
    payload = (RECEIPT_HEADER + 'R1,BK-A,00106,50.54\n').encode()
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: service.attach(anchor, payload), range(4)))
    assert all(item['ready'] is True for item in outcomes)
    state = client.get(f'/api/claim/{anchor}').json()
    assert len(state['writeoffs']) == 1 and state['counts']['claimed'] == 1


def test_export_carries_claim_evidence(client, anchor):
    sync(client, anchor, ('BK-A', '50.54'))
    attach(client, anchor, ('R1', 'BK-A', '00106', '50.54'))
    proof = client.get(f'/api/export/{anchor}').json()['claim']
    assert proof['ready'] is True
    assert proof['writeoffs'] == [{
        'flow_id': 'BK-A', 'key': '00106', 'amount': '50.54',
        'receipt_line': 2, 'created': proof['writeoffs'][0]['created']}]
    assert proof['receipts'][0]['receipt_id'] == 'R1'


def test_gb18030_flow_accepted(client, anchor):
    from base64 import b64encode
    payload = b64encode((FLOW_HEADER + 'BK-A,50.54\n').encode('gb18030')).decode()
    response = client.post(f'/api/claim/{anchor}/sync', json={'flows_base64': payload})
    assert response.status_code == 200
    assert response.json()['flows'][0]['status'] == 'CANDIDATE'


def test_replacing_flows_keeps_evidence_and_locks_statement(client, anchor):
    sync(client, anchor, ('BK-A', '50.54'))
    attach(client, anchor, ('R1', 'BK-A', '00106', '50.54'))
    # 整批换成另一笔流水：旧回单与核销留痕，00106 不得回流候选池再抵新流水。
    state = sync(client, anchor, ('BK-B', '90.00')).json()
    assert len(state['writeoffs']) == 1
    owner = next(s['flow_id'] for s in state['statements'] if s['key'] == '00106')
    assert owner == 'BK-A'
    candidates = state['flows'][0]['candidates']
    assert all('00106' not in group for group in candidates)
