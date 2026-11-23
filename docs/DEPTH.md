# 纸上版税业务与测试登记

- 规模：中型
- 使用者：出版社发行核算员
- 核心规则：以年初净销量为起点分段计提，退货逆冲最高已占档，再按当期净额和前期准备金结算。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 渠道回执 | 检查编码、字段宽度和来源行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 合同字段 | 归一修订、业务键和偏移时间 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 争议结算单 | 定位重复、被替代与矛盾来源 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 版税核算 | 按规则复算并追溯证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 财务勾稽 | 核对独立清单和各类差异 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 月结批次 | 打开历史批次并对原文件复跑 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 会签底稿 | 登记复核结论并下载证据 | `POST /api/review/{run_id}` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 扣款认领 | 扣款流水对结算单，回单定归属后核销 | `POST /api/claim/{run_id}/sync` | `app/modules/claim/engine.py` | `tests/test_claim.py` |

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-01 | GB18030 来源文件 | legacy.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_gb18030` |
| TRAP-02 | BOM 前缀 | shift.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 备注含引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 分段重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不足 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 缺测哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 前导零的单号 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时刻 UTC 归一 | shift.csv | `app/modules/domain/values.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 同版业务字段冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-16 | 末行引号截断 | truncated.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_truncated_rejected` |
| TRAP-17 | 旧版列名映射 | legacy.csv | `app/modules/contract/schema.py` | `tests/test_contract.py::test_legacy_aliased` |
| TRAP-18 | 空文件、空白文件与仅表头 | 测试构造 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核版本拒绝 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-31 | 两组合额先认领会串账 | bank_flows.csv | `app/modules/claim/engine.py` | `tests/test_claim.py::test_equal_amount_groups_stay_pending` |
| TRAP-32 | 重跑重复核销/已核销单再抵另一笔 | 测试构造 | `app/modules/claim/repository.py` | `tests/test_claim.py::test_rerun_keeps_writeoffs_and_never_duplicates` |
| TRAP-33 | 无凭据候选不得会签确认 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_claim.py::test_receipt_only_writeoff_and_gate` |
| TRAP-10 | half cent | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_half_cent` |
| TRAP-104 | reverse higher | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_reverse_higher` |

## 对账

输入 = 计入 + 隔离 + 重传及版本替换 + 空白记录 + 重复表头。按业务键全外连接，缺失一侧与数值为零分别登记。逐笔差值与总差一致。

## 扣款认领

银行可把多张结算单并成一笔扣款。扣款流水与本批结算单应付对账：先按银行回单（`银行回单号,扣款流水号,结算单号,回单金额(元)`）核销，回单金额必须与结算单应付逐张相等；无回单流水在未核销结算单池中做子集匹配，唯一解记为「唯一候选·缺回单」，存在两组及以上同额组合时一律「待认领」，无解或回单合计不足记「金额差异」。

已核销结算单从候选池剔除，不能再抵另一笔扣款；核销按 `(批次,流水,结算单)` 与回单行唯一约束落库，重跑流水或重复补回单均幂等。会签确认前检查：只要存在未凭回单核销的扣款即拒绝（`CLAIM_PENDING`），退回结论不受此限。
