"""Single-file HTML reporter (no Allure server, no external assets).

Everything — CSS, JS, request/response payloads — is embedded into one .html
file so a CI job can upload it as an artifact and anyone can open it offline.
Credentials in request headers are redacted before they ever reach the file.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from flowtest.core.models import CaseResult, RunResult, Status
from flowtest.utils.helpers import json_dumps, shorten

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@</title>
<style>
:root{
  --bg:#f5f7fb; --card:#ffffff; --border:#e4e9f0; --text:#1f2937; --muted:#6b7280;
  --green:#16a34a; --green-bg:#ecfdf5; --red:#dc2626; --red-bg:#fef2f2;
  --amber:#d97706; --amber-bg:#fffbeb; --gray:#64748b; --gray-bg:#f1f5f9;
  --blue:#2563eb; --blue-bg:#eff6ff;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  font-size:14px;line-height:1.6}
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 60px}
header{background:linear-gradient(120deg,#eef4ff,#f8fbff);border:1px solid var(--border);
  border-radius:16px;padding:24px 28px;margin-bottom:20px}
header h1{margin:0 0 6px;font-size:24px;letter-spacing:-.4px}
header .sub{color:var(--muted);font-size:13px}
header .sub b{color:var(--text);font-weight:600}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.b-passed{background:var(--green-bg);color:var(--green)}
.b-failed,.b-error{background:var(--red-bg);color:var(--red)}
.b-skipped{background:var(--gray-bg);color:var(--gray)}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px 18px}
.stat .n{font-size:26px;font-weight:700;line-height:1.2}
.stat .l{color:var(--muted);font-size:12px;margin-top:2px}
.stat.ok .n{color:var(--green)} .stat.bad .n{color:var(--red)}
.stat.rate .n{color:var(--blue)} .stat.skip .n{color:var(--gray)}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px;
  position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:5}
button.f{border:1px solid var(--border);background:var(--card);color:var(--text);
  padding:6px 14px;border-radius:8px;cursor:pointer;font-size:13px}
button.f:hover{border-color:var(--blue)}
button.f.active{background:var(--blue);color:#fff;border-color:var(--blue)}
#q{flex:1;min-width:180px;padding:7px 12px;border:1px solid var(--border);
  border-radius:8px;background:var(--card);color:var(--text);outline:none}
#q:focus{border-color:var(--blue)}
.case{background:var(--card);border:1px solid var(--border);border-radius:12px;
  margin-bottom:10px;overflow:hidden}
.case-head{display:flex;align-items:center;gap:12px;padding:13px 16px;cursor:pointer;user-select:none}
.case-head:hover{background:#fafbfe}
.case-head .arrow{color:var(--muted);font-size:12px;transition:transform .15s;width:12px}
.case.open .arrow{transform:rotate(90deg)}
.cid{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-weight:600;font-size:13px}
.cname{color:var(--muted);font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.method{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--blue);
  background:var(--blue-bg);padding:2px 8px;border-radius:6px}
.url{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--muted);
  max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dur{color:var(--muted);font-size:12px;min-width:64px;text-align:right}
.case-body{display:none;border-top:1px solid var(--border);padding:16px;background:#fcfdff}
.case.open .case-body{display:block}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.panel{border:1px solid var(--border);border-radius:10px;background:#fff;overflow:hidden}
.panel h4{margin:0;padding:9px 13px;font-size:12px;font-weight:600;color:var(--muted);
  background:#f8fafc;border-bottom:1px solid var(--border);letter-spacing:.3px}
.panel .inner{padding:12px 13px}
pre{margin:0;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;
  white-space:pre-wrap;word-break:break-all;color:#334155;line-height:1.55}
.kv{display:grid;grid-template-columns:110px 1fr;gap:4px 10px;font-size:12px;margin-bottom:10px}
.kv .k{color:var(--muted)}
.kv .v{font-family:ui-monospace,Consolas,monospace;word-break:break-all}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;color:var(--muted);font-weight:600;padding:7px 9px;border-bottom:1px solid var(--border);background:#f8fafc}
td{padding:7px 9px;border-bottom:1px solid #f1f5f9;vertical-align:top;word-break:break-all}
tr:last-child td{border-bottom:none}
td.mono,th.mono{font-family:ui-monospace,Consolas,monospace}
.pill{padding:1px 8px;border-radius:6px;font-size:11px;font-weight:600}
.pill.ok{background:var(--green-bg);color:var(--green)}
.pill.no{background:var(--red-bg);color:var(--red)}
.soft{background:var(--amber-bg);color:var(--amber)}
.alert{padding:9px 12px;border-radius:8px;font-size:12px;margin-bottom:12px}
.alert.warn{background:var(--amber-bg);color:var(--amber);border:1px solid #fde68a}
.alert.err{background:var(--red-bg);color:var(--red);border:1px solid #fecaca}
.meta{color:var(--muted);font-size:12px;margin-bottom:10px}
.tags span{display:inline-block;background:var(--gray-bg);color:var(--gray);
  border-radius:5px;padding:1px 7px;font-size:11px;margin-right:5px}
footer{margin-top:26px;color:var(--muted);font-size:12px;text-align:center;line-height:1.9}
.empty{text-align:center;color:var(--muted);padding:40px;display:none}
@media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>@@TITLE@@</h1>
  <div class="sub">套件 <b>@@SUITE@@</b> &nbsp;·&nbsp; 环境 <b>@@BASE_URL@@</b> &nbsp;·&nbsp;
    开始 <b>@@STARTED@@</b> &nbsp;·&nbsp; 总耗时 <b>@@DURATION@@ ms</b></div>
  <div class="sub" style="margin-top:6px">FlowTest @@VERSION@@ &nbsp;·&nbsp; Python @@PY@@ &nbsp;·&nbsp;
    并发度 @@PARALLEL@@ &nbsp;·&nbsp; 软断言 @@SOFT@@</div>
</header>

<div class="stats">
  <div class="stat"><div class="n">@@TOTAL@@</div><div class="l">用例总数</div></div>
  <div class="stat ok"><div class="n">@@PASSED@@</div><div class="l">通过</div></div>
  <div class="stat bad"><div class="n">@@FAILED@@</div><div class="l">失败 / 异常</div></div>
  <div class="stat skip"><div class="n">@@SKIPPED@@</div><div class="l">跳过</div></div>
  <div class="stat rate"><div class="n">@@RATE@@%</div><div class="l">通过率</div></div>
</div>

<div class="toolbar">
  <button class="f active" data-f="all">全部</button>
  <button class="f" data-f="passed">通过</button>
  <button class="f" data-f="failed">失败</button>
  <button class="f" data-f="skipped">跳过</button>
  <input id="q" placeholder="搜索用例 id / 名称 / URL ...">
</div>

<div id="cases">@@BODY@@</div>
<div class="empty" id="empty">没有匹配的用例</div>

<footer>
  Generated by FlowTest · 单文件离线报告，可直接作为 CI artifact 分享<br>
  报告中的请求头已自动脱敏（Authorization / Token / Cookie 等）
</footer>
</div>
<script>
document.querySelectorAll('.case-head').forEach(function(h){
  h.addEventListener('click',function(){h.parentElement.classList.toggle('open');});
});
var current='all';
function apply(){
  var q=document.getElementById('q').value.toLowerCase();var shown=0;
  document.querySelectorAll('.case').forEach(function(c){
    var st=c.dataset.status;var text=c.dataset.search.toLowerCase();
    var okF=(current==='all')||(current==='failed'?(st==='failed'||st==='error'):st===current);
    var okQ=!q||text.indexOf(q)>=0;
    c.style.display=(okF&&okQ)?'':'none';if(okF&&okQ)shown++;
  });
  document.getElementById('empty').style.display=shown?'none':'block';
}
document.querySelectorAll('button.f').forEach(function(b){
  b.addEventListener('click',function(){
    document.querySelectorAll('button.f').forEach(function(x){x.classList.remove('active');});
    b.classList.add('active');current=b.dataset.f;apply();
  });
});
document.getElementById('q').addEventListener('input',apply);
</script>
</body>
</html>
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fmt(value: Any, limit: int = 260) -> str:
    if value is None:
        return '<span style="color:#94a3b8">null</span>'
    if isinstance(value, (dict, list, tuple)):
        return _esc(shorten(json_dumps(value, pretty=False), limit))
    return _esc(shorten(value, limit))


def _pre(value: Any) -> str:
    if value is None or value == {} or value == []:
        return '<span style="color:#94a3b8">（空）</span>'
    return f"<pre>{_esc(json_dumps(value))}</pre>"


def _assertion_rows(result: CaseResult) -> str:
    last = result.last
    if not last or not last.assertions:
        return '<tr><td colspan="6" style="color:#94a3b8">无断言记录</td></tr>'
    rows = []
    for i, a in enumerate(last.assertions, start=1):
        pill = '<span class="pill ok">PASS</span>' if a.passed else '<span class="pill no">FAIL</span>'
        soft = ' <span class="pill soft">SOFT</span>' if a.soft else ""
        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td class='mono'>{_esc(a.op)}</td>"
            f"<td class='mono'>{_esc(a.check or '-')}</td>"
            f"<td class='mono'>{_fmt(a.expect)}</td>"
            f"<td class='mono'>{_fmt(a.actual)}</td>"
            f"<td>{pill}{soft}<div style='color:#6b7280;font-size:11px;margin-top:3px'>{_esc(shorten(a.message, 200))}</div></td>"
            "</tr>"
        )
    return "".join(rows)


def _render_case(result: CaseResult, index: int) -> str:
    case = result.case
    status = result.status.value
    badge = f'<span class="badge b-{status}">{status.upper()}</span>'
    last = result.last
    request = (last.request if last else {}) or {}
    response = (last.response if last else {}) or {}

    alerts = ""
    if result.skip_reason and result.status is Status.SKIPPED:
        alerts += f'<div class="alert warn">跳过原因：{_esc(result.skip_reason)}</div>'
    if last and last.error:
        alerts += f'<div class="alert err">请求异常：{_esc(last.error)}</div>'

    tags = "".join(f"<span>{_esc(t)}</span>" for t in case.tags)
    deps = ", ".join(f"<code>{_esc(d)}</code>" for d in case.depends_on) or "无"
    tags_html = f' &nbsp;·&nbsp; <span class="tags">{tags}</span>' if tags else ""
    meta = (
        f'<div class="meta">#{index} &nbsp;·&nbsp; 来源 <code>{_esc(case.source)}</code>'
        f" &nbsp;·&nbsp; 依赖 {deps}"
        f" &nbsp;·&nbsp; 重试上限 {case.retry}"
        f" &nbsp;·&nbsp; 提取变量 {len(case.extract)} 个"
        f" &nbsp;·&nbsp; 断言 {len(case.validate)} 条"
        + tags_html
        + "</div>"
    )

    request_kv = (
        '<div class="kv">'
        f'<div class="k">Method</div><div class="v">{_esc(request.get("method", "-"))}</div>'
        f'<div class="k">URL</div><div class="v">{_esc(request.get("url", "-"))}</div>'
        f'<div class="k">Timeout</div><div class="v">{_esc(request.get("timeout", "-"))} s</div>'
        "</div>"
        f'<div class="panel" style="margin-top:10px"><h4>HEADERS</h4><div class="inner">{_pre(request.get("headers"))}</div></div>'
        f'<div class="panel" style="margin-top:10px"><h4>QUERY / BODY</h4><div class="inner">{_pre(request.get("body") or request.get("params"))}</div></div>'
    )
    response_kv = (
        '<div class="kv">'
        f'<div class="k">Status</div><div class="v">{_esc(response.get("status_code", "-"))}</div>'
        f'<div class="k">耗时</div><div class="v">{_esc(response.get("elapsed_ms", "-"))} ms</div>'
        f'<div class="k">Attempts</div><div class="v">{len(result.attempts)}</div>'
        "</div>"
        f'<div class="panel"><h4>RESPONSE BODY</h4><div class="inner">{_pre(response.get("body"))}</div></div>'
    )
    attempts_panel = ""
    if len(result.attempts) > 1:
        rows = []
        for i, attempt in enumerate(result.attempts, start=1):
            status = attempt.response.get("status_code", "-") if attempt.response else "-"
            if attempt.error:
                outcome = "请求异常"
            elif status in (200, 201, 202, 204):
                outcome = "成功"
            else:
                outcome = "可重试状态"
            rows.append(
                f"<tr><td>{i}</td><td class='mono'>{_esc(status)}</td>"
                f"<td class='mono'>{attempt.elapsed_ms:.0f} ms</td>"
                f"<td>{_esc(outcome)}</td>"
                f"<td class='mono'>{_esc(shorten(attempt.error or '-', 120))}</td></tr>"
            )
        attempts_panel = (
            '<div class="panel" style="margin-top:14px"><h4>重试轨迹（仅网络异常 / 5xx 触发重试）</h4>'
            "<table><thead><tr><th>#</th><th>HTTP</th><th>耗时</th><th>结果</th><th>异常信息</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        )

    extracted = (
        f'<div class="panel" style="margin-top:14px"><h4>提取并传递给下游的变量</h4>'
        f'<div class="inner">{_pre(result.extracted) if result.extracted else "<span style=color:#94a3b8>（无）</span>"}</div></div>'
    )
    assertions = (
        '<div class="panel" style="margin-top:14px"><h4>断言明细</h4>'
        '<table><thead><tr><th>#</th><th>算子</th><th>取值路径</th><th>期望</th><th>实际</th><th>结果</th></tr></thead>'
        f"<tbody>{_assertion_rows(result)}</tbody></table></div>"
    )

    search = f"{case.id} {case.name} {case.request.url} {' '.join(case.tags)}".lower()
    opened = " open" if result.status in (Status.FAILED, Status.ERROR) else ""
    return (
        f'<div class="case{opened}" data-status="{status}" data-search="{_esc(search)}">'
        '<div class="case-head">'
        f'<span class="arrow">&#9654;</span>{badge}'
        f'<span class="cid">{_esc(case.id)}</span>'
        f'<span class="cname">{_esc(case.name or case.description or "-")}</span>'
        f'<span class="method">{_esc(case.request.method)}</span>'
        f'<span class="url">{_esc(case.request.url)}</span>'
        f'<span class="dur">{result.elapsed_ms:.0f} ms</span>'
        "</div>"
        f'<div class="case-body">{alerts}{meta}{attempts_panel}<div class="row" style="margin-top:14px">'
        f'<div class="panel"><h4>REQUEST</h4><div class="inner">{request_kv}</div></div>'
        f'<div class="panel"><h4>RESPONSE</h4><div class="inner">{response_kv}</div></div>'
        f"</div>{assertions}{extracted}</div></div>"
    )


def render_html(result: RunResult) -> str:
    env = result.environment
    body = "".join(_render_case(r, i) for i, r in enumerate(result.results, start=1))
    replacements = {
        "@@TITLE@@": _esc(f"FlowTest 测试报告 · {result.suite_name}"),
        "@@SUITE@@": _esc(result.suite_name),
        "@@BASE_URL@@": _esc(result.base_url or "-"),
        "@@STARTED@@": _esc(result.started_at),
        "@@DURATION@@": f"{result.duration_ms:.0f}",
        "@@VERSION@@": _esc(env.get("flowtest", "-")),
        "@@PY@@": _esc(env.get("python", "-")),
        "@@PARALLEL@@": _esc(env.get("parallel", 1)),
        "@@SOFT@@": "开启" if env.get("soft_assert") else "关闭",
        "@@TOTAL@@": str(result.total),
        "@@PASSED@@": str(result.passed),
        "@@FAILED@@": str(result.failed),
        "@@SKIPPED@@": str(result.skipped),
        "@@RATE@@": f"{result.pass_rate:.1f}",
    }
    page = _TEMPLATE
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page.replace("@@BODY@@", body)


def write_report(result: RunResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(result), encoding="utf-8")
    return target
