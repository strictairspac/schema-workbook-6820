const RANK = {queued: 0, running: 1, completed: 2, failed: 2};

const rank = status => RANK[status] ?? 0;

function mergeOne(previous, incoming) {
  if (!previous) return incoming;
  if (rank(incoming.status) < rank(previous.status)) return previous;
  if (rank(incoming.status) === 2 && incoming.status !== previous.status) return previous;
  if (incoming.status === 'completed' && incoming.result == null) {
    return previous.result != null ? {...incoming, result: previous.result} : previous;
  }
  return incoming;
}

/** 合并同一会话的前后两次列表响应：状态只前进，正文不因乱序丢失。 */
export function mergeReports(previous, incoming) {
  const byId = new Map(previous.map(item => [item.id, item]));
  for (const item of incoming) byId.set(item.id, mergeOne(byId.get(item.id), item));
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

/** 详情同理：慢响应不能把已读到的完成态刷回排队。 */
export function mergeReport(previous, incoming) {
  if (!previous || previous.id !== incoming.id) return incoming;
  return mergeOne(previous, incoming);
}
