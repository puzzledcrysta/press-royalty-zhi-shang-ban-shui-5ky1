REASONS = {
    'EMPTY': '文件无内容', 'BLANK_FILE': '文件只有空白', 'HEADER_ONLY': '文件只有表头',
    'ENCODING': '无法识别编码', 'CSV': '表格语法错误', 'HEADER': '表头无效',
    'WIDTH': '列数与表头不一致', 'CONTRACT': '列契约无法应用', 'REQUIRED': '主键或业务字段缺失',
    'TIMESTAMP': '时间需包含偏移量', 'NUMBER': '数字无法归一', 'RANGE': '数字越界',
    'EXACT_DUP': '同版本重复传输', 'SUPERSEDED': '已被更新版本代替',
    'REV_CONFLICT': '最高版本证据有冲突', 'BUSINESS': '业务规则无法判定',
    'MISSING_BOOK': '外部账缺少业务键', 'MISSING_RESULT': '复算结果缺少业务键',
    'AMOUNT_DELTA': '复算与外部账计量不同', 'BOOK_CONFLICT': '独立账含重复业务键',
    'RUN_UNKNOWN': '没有此批次', 'DEMO_UNKNOWN': '没有此样例', 'STALE': '复核版本已过期',
    'REVIEW_NOTE': '有差异时须填写复核意见', 'REVIEW_DECISION': '复核结论无效',
    'FLOW_HEADER': '扣款流水表头无效', 'FLOW_WIDTH': '扣款流水列数不符', 'FLOW_CONFLICT': '扣款流水号重复',
    'RECEIPT_HEADER': '银行回单表头无效', 'RECEIPT_WIDTH': '银行回单列数不符', 'RECEIPT_DUP': '同一回单重复上传',
    'RECEIPT_FLOW': '回单指向未知扣款流水', 'RECEIPT_STATEMENT': '回单指向未知结算单',
    'RECEIPT_AMOUNT': '回单金额与结算单应付不符', 'RECEIPT_USED': '该结算单已被其他扣款核销',
    'CLAIM_PENDING': '尚有扣款无凭据归属，不能会签确认', 'CLAIM_AMOUNT': '扣款金额与归属结算单合计不符',
}

CLAIM_STATUS = {
    'WRITE_OFF': '凭据核销', 'CANDIDATE': '唯一候选·缺回单', 'PENDING': '待认领', 'DIFFERENCE': '金额差异',
}

REASONS.update({'ROYALTY_TIER': '合同费档无效', 'ROYALTY_RETURNS': '退量超累计销量', 'DATE': '日期格式无效', 'REV_BLOCKED': '较新来源尚未采信'})
