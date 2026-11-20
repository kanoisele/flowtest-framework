"""Command line entry point.

`flowtest demo` is the important one: it starts the built-in SUT, runs the
bundled example suite, writes an HTML report and shuts everything down — a
fresh clone can be verified with two commands and zero external services.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
import yaml

from flowtest import __version__
from flowtest.core.assertor import Assertor
from flowtest.core.client import HttpClient
from flowtest.core.loader import load_suite, load_suite_lenient
from flowtest.core.resolver import describe_plan
from flowtest.core.runner import Runner, RunnerConfig
from flowtest.mock.demo_server import start_demo_server, stop_demo_server
from flowtest.report.html import write_report
from flowtest.utils.logger import log

BUNDLED = Path(__file__).resolve().parent / "examples"

_MARK = {"passed": "[PASS]", "failed": "[FAIL]", "error": "[ERR ]", "skipped": "[SKIP]"}

_OP_DOCS = {
    "eq": "等于", "ne": "不等于", "gt": "大于", "ge": "大于等于", "lt": "小于", "le": "小于等于",
    "contains": "包含（字符串 / 列表 / 字典 key）", "not_contains": "不包含",
    "in": "属于集合", "not_in": "不属于集合", "regex": "正则匹配",
    "startswith": "前缀", "endswith": "后缀", "len_eq": "长度等于", "len_ge": "长度不小于",
    "is_null": "为 null", "not_null": "非 null", "exists": "路径存在", "not_exists": "路径不存在",
    "type": "类型名（int/str/list/dict/none...）", "schema": "JSON Schema 契约校验",
}


def _print_summary(result) -> None:
    click.echo("")
    click.echo("─" * 78)
    for r in result.results:
        line = f"{_MARK[r.status.value]} {r.case.id:<30} {r.elapsed_ms:8.0f} ms"
        if r.failed_assertions:
            detail = " | ".join(a.message for a in r.failed_assertions[:2])
            line += f"  {detail[:90]}"
        elif r.skip_reason:
            line += f"  {r.skip_reason[:90]}"
        click.echo(line)
    click.echo("─" * 78)
    click.echo(
        f"合计 {result.total} 条 | 通过 {result.passed} | 失败 {result.failed} | "
        f"跳过 {result.skipped} | 通过率 {result.pass_rate:.1f}% | 耗时 {result.duration_ms:.0f} ms"
    )


def _parse_vars(items: tuple[str, ...]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise click.BadParameter(f"--var 需要 KEY=VALUE 格式，收到 {item!r}")
        key, raw = item.split("=", 1)
        try:
            parsed[key.strip()] = yaml.safe_load(raw)
        except yaml.YAMLError:
            parsed[key.strip()] = raw
    return parsed


def _execute(
    path: str,
    base_url: str | None,
    parallel: int,
    soft: bool,
    fail_fast: bool,
    report: str,
    no_report: bool,
    variables: tuple[str, ...],
):
    suite = load_suite(path, base_url=base_url, extra_vars=_parse_vars(variables))
    client = HttpClient(base_url=suite.base_url, default_headers=suite.headers)
    config = RunnerConfig(parallel=parallel, soft=soft, fail_fast=fail_fast)
    try:
        result = Runner(suite, client, config).run()
    finally:
        client.close()
    _print_summary(result)
    if not no_report:
        target = write_report(result, report)
        click.echo(f"HTML 报告: {target.resolve()}")
    return result


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="flowtest")
def main() -> None:
    """FlowTest — DAG 驱动的轻量级接口自动化测试框架。"""


@main.command()
@click.argument("path", default="testcases", type=click.Path(exists=True))
@click.option("--base-url", default=None, help="覆盖用例集里的 base_url")
@click.option("-p", "--parallel", default=1, show_default=True, help="同层用例并发度")
@click.option("--soft", is_flag=True, help="全局开启软断言（收集全部失败点）")
@click.option("--fail-fast", is_flag=True, help="出现失败后跳过后续层")
@click.option("--report", default="report.html", show_default=True, help="HTML 报告输出路径")
@click.option("--no-report", is_flag=True, help="不生成 HTML 报告")
@click.option("--var", "variables", multiple=True, help="注入变量 KEY=VALUE，可重复")
def run(path, base_url, parallel, soft, fail_fast, report, no_report, variables):
    """执行一个用例文件或整个用例目录。"""
    result = _execute(path, base_url, parallel, soft, fail_fast, report, no_report, variables)
    sys.exit(0 if result.ok else 1)


@main.command()
@click.option("--port", default=0, show_default=True, help="Demo 服务端口，0 表示自动分配")
@click.option("-p", "--parallel", default=2, show_default=True, help="同层用例并发度")
@click.option("--soft", is_flag=True, help="全局开启软断言")
@click.option("--report", default="report.html", show_default=True, help="HTML 报告输出路径")
def demo(port, parallel, soft, report):
    """一键体验：启动内置被测服务 → 跑示例用例 → 生成报告 → 关闭服务。"""
    cases = BUNDLED / "testcases"
    if not cases.is_dir():
        cases = Path("testcases")
    server, url = start_demo_server(port)
    click.echo(f"内置 Demo 服务已启动: {url}")
    try:
        result = _execute(str(cases), url, parallel, soft, False, report, False, ())
        click.echo(f"Demo 服务已关闭（{url}）")
    finally:
        stop_demo_server(server)
    sys.exit(0 if result.ok else 1)


@main.command()
@click.argument("path", default="testcases", type=click.Path(exists=True))
def validate(path):
    """只做 DSL 静态校验并打印 DAG 执行计划（不发任何请求）。"""
    suite, problems = load_suite_lenient(path)
    if problems:
        click.echo(f"静态校验发现 {len(problems)} 个问题：", err=True)
        for problem in problems:
            click.echo(f"  - {problem}", err=True)
        sys.exit(1)
    assert suite is not None
    click.echo(f"静态校验通过：{len(suite.active_cases)} 个启用用例，"
               f"{len(suite.cases) - len(suite.active_cases)} 个禁用用例")
    click.echo(
        f"断言算子 {len(Assertor.available_ops()) + 1} 种（含 schema 契约校验），"
        f"base_url = {suite.base_url or '(未配置)'}"
    )
    click.echo("\nDAG 执行计划（同一层可并行）：")
    click.echo(describe_plan(suite.active_cases))


@main.command()
def ops():
    """列出全部可用断言算子。"""
    click.echo(f"FlowTest 共支持 {len(Assertor.available_ops()) + 1} 种断言算子：\n")
    for name in sorted(Assertor.available_ops() + ["schema"]):
        click.echo(f"  {name:<14} {_OP_DOCS.get(name, '')}")


_SMOKE_YAML = """name: 我的第一个 FlowTest 用例集
base_url: http://127.0.0.1:8899
variables:
  expected_status: 200
cases:
  - id: health_check
    name: 健康检查
    tags: [smoke]
    request:
      method: GET
      url: /health
    validate:
      - check: status_code
        op: eq
        expect: ${expected_status}
      - check: $.data.status
        op: eq
        expect: UP
      - check: elapsed_ms
        op: lt
        expect: 2000
"""


@main.command()
@click.argument("target", default="flowtest-project", type=click.Path())
def init(target):
    """在当前目录生成一个最小可运行的用例模板工程。"""
    root = Path(target)
    (root / "testcases").mkdir(parents=True, exist_ok=True)
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "testcases" / "smoke.yaml").write_text(_SMOKE_YAML, encoding="utf-8")
    (root / "README.md").write_text(
        "# FlowTest 用例工程\n\n"
        "```bash\nflowtest validate testcases\nflowtest run testcases --base-url http://127.0.0.1:8899\n```\n",
        encoding="utf-8",
    )
    click.echo(f"已生成 {root.resolve()}")
    click.echo("下一步：flowtest validate testcases")


if __name__ == "__main__":  # pragma: no cover
    log.debug("cli boot")
    main()
