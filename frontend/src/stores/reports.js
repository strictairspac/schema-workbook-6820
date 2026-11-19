import {reportsApi} from '../api/reports.js';
import {mergeReports} from '../utils/reports.js';

/**
 * 报告列表状态：并发刷新请求可能乱序返回，这里只接受新发出的那次响应，
 * 并把“完成”保留住，避免慢响应或复制延迟把完成刷回排队。
 */
export const reportsStore = {
  items: [],
  readSource: null,
  unavailable: null,
  seq: 0,
  async refresh() {
    const ticket = ++this.seq;
    try {
      const payload = await reportsApi.list();
      if (ticket !== this.seq) return this.items;
      const items = Array.isArray(payload) ? payload : payload.items || [];
      this.items = mergeReports(this.items, items);
      this.readSource = Array.isArray(payload) ? null : payload.read_source || null;
      this.unavailable = null;
    } catch (error) {
      if (ticket !== this.seq) return this.items;
      // 主库中断且本会话进度尚未复制到从库：保留已读内容，明确提示暂不可用。
      this.unavailable = error.message;
    }
    return this.items;
  },
};
