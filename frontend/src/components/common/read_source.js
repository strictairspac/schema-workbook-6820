const SOURCE_LABELS = {primary: '主库', replica: '从库', mixed: '从库 + 主库补齐'};

const sourceLabel = source => SOURCE_LABELS[source] || source;

/** 列表/详情页上的读取来源标注：这次实际读的是主库还是从库。 */
export function readSourceNote(source, scope = '列表') {
  if (!source) return '';
  const detail = source === 'primary'
    ? '数据直接来自主库'
    : source === 'replica'
      ? '数据来自只读从库'
      : '从库为主，缺口已回主库补齐';
  return `<p class="read-source" data-source="${source}"><span class="live-dot"></span>${scope}读取：<strong>${sourceLabel(source)}</strong><small>${detail}</small></p>`;
}

/** 表格行内的紧凑来源标记。 */
export function sourceBadge(source) {
  if (!source) return '';
  return `<span class="source-badge ${source}">${sourceLabel(source)}</span>`;
}
