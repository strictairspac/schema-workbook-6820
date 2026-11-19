import { session } from '../hooks/session.js';
import { readSessionId } from '../hooks/read_session.js';

function headers(token) {
  return {
    'Content-Type': 'application/json',
    'X-Read-Session': readSessionId(),
    ...(token ? { Authorization: 'Bearer ' + token } : {}),
  };
}

async function parse(res) {
  const result = await res.json().catch(() => ({}));
  if (!res.ok) throw Error(typeof result.detail === 'string' ? result.detail : '输入格式有误，请检查数值和必填项');
  return result;
}

export async function api(path, method = 'GET', data) {
  const res = await fetch('/api' + path, {
    method,
    headers: headers(session.token),
    body: data ? JSON.stringify(data) : undefined,
  });
  return parse(res);
}

export async function download(id) {
  const res = await fetch('/api/reports/' + id + '/export', { headers: headers(session.token) });
  if (!res.ok) throw Error('导出失败，请重新登录后重试');
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = 'report-' + id + '.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
