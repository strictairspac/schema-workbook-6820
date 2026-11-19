const KEY = 'schemaworkbook-read-session';

/** 每个标签页一个稳定的阅读会话标识，后端据此维护“读己之写 + 不倒退”的进度下界。 */
function create() {
  const value = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  try { sessionStorage.setItem(KEY, value); } catch { /* 隐私模式下降级为内存值 */ }
  return value;
}

let cached = null;

export function readSessionId() {
  if (cached) return cached;
  let stored = null;
  try { stored = sessionStorage.getItem(KEY); } catch { /* ignore */ }
  cached = stored || create();
  return cached;
}
