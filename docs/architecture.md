# FlowTest 架构设计与决策记录

面向面试准备：不只要能说「我做了什么」，更要能说「为什么这么做、放弃了什么、如果重来会怎么改」。

---

## 1. 分层与模块职责

| 层 | 模块 | 职责 | 不负责什么 |
| --- | --- | --- | --- |
| 数据模型 | `core/models.py` | 纯 dataclass：`Case` / `Suite` / `Response` / `RunResult` | 不做 IO、不依赖 requests |
| 加载层 | `core/loader.py` | YAML → 模型、Schema 文件解析、**静态校验** | 不发请求 |
| 编排层 | `core/resolver.py` | 依赖图校验、拓扑分层、环检测 | 不执行用例 |
| 运行时 | `core/context.py`、`extractor.py` | 变量池、模板渲染、响应取值 | 不做断言 |
| 校验层 | `core/assertor.py` | 算子注册表、软断言、Schema 校验 | 不发起 HTTP |
| 传输层 | `core/client.py` | Session 管理、计时、JSON 解析 | 不理解业务语义 |
| 调度层 | `core/runner.py` | 分层并发、重试、Skip 传播、结果汇总 | 不拼 HTML |
| 展示层 | `report/html.py` | 单文件 HTML 渲染、脱敏展示 | 不修改结果 |

**依赖方向是单向的**：`runner` 依赖下层，下层不反向依赖 `runner`。报告层只消费 `RunResult`，所以换一个报告实现（JUnit XML / Allure）不需要动执行引擎。

---

## 2. 关键设计决策（ADR）

### ADR-1：自研执行引擎，而不是给 pytest 写插件

- **选择**：自己实现 loader → resolver → runner 全链路。
- **理由**：pytest 的收集模型是「文件/函数」的扁平列表，用例间的**数据依赖**和**同层并发**不是它的原生抽象；要硬塞进去反而要跟 hook 体系打架。自研 runner 能完全控制执行顺序、重试粒度和结果结构。
- **代价**：放弃了 pytest 生态（fixture、插件、mark、IDE 集成）。
- **怎么补**：框架本身仍用 pytest 做自测；后续可提供 `pytest-flowtest` 插件把 case 暴露成 pytest item。
- **面试话术**：「我不是觉得 pytest 不好，而是用例依赖编排这件事的抽象层级和 pytest 的收集模型不匹配；但测试框架自身的质量仍然靠 pytest 保障。」

### ADR-2：分层 DAG（Kahn）而非「按文件顺序执行」

- 入度 = 依赖数；每轮取出所有入度为 0 的节点构成一层，层内互不依赖 → 可并行；层间严格串行 → 变量传递确定。
- 复杂度 O(V + E)；另做一次 DFS 专门为了**打印出可读的环路径**（`a -> b -> c -> a`），比只报「存在环」好用得多。
- 代价：并行度受限于层宽度，不能做全局最优调度。

### ADR-3：变量按 `<case_id>.<var>` 命名空间

- `${login.token}` 只能来自 `login` 用例的 `extract`，来源可静态推导，也因此能在加载期检查「有没有引用没人产出的变量」。
- 整串 token（`"${count}"`）渲染时**保留原始 Python 类型**，否则 `expect: 3` 会变成 `"3"` 导致数值断言假失败。
- 内置 `${{uuid()}}` / `${{random_int(1,5)}}` 在**每次重试重新求值**，便于构造幂等性/唯一性数据。

### ADR-4：只对网络异常与 5xx 重试，断言失败绝不重试

- 断言失败是产品信号，重试可能把它「洗」成偶发通过，制造 flaky 测试。
- 5xx / 连接错误属于环境抖动，指数退避重试有价值。
- 报告保留**完整重试轨迹**，而不是只显示最后一次。

### ADR-5：`threading.local()` 隔离 `requests.Session`

- `requests.Session` 官方文档未保证线程安全；层内并发时共享 Session 会有连接池状态与 Cookie 串扰风险。
- 每线程懒加载独立 Session，同时复用该线程内的连接（keep-alive）。

### ADR-6：单文件 HTML 报告，而不是 Allure

- Allure 需要 Java/服务/额外命令，clone 项目的人往往跑不起来；CI artifact 也不能直接双击看。
- 单文件报告：内嵌 CSS/JS、失败用例默认展开、请求头自动脱敏、支持筛选搜索，可直接上传 artifact。
- 代价：没有历史趋势、没有多批次对比。这一条要主动承认。

### ADR-7：错误前置（Shift-left）

加载期一次性检查：id 唯一、依赖存在且成环与否、算子名、JSONPath 语法、Schema 文件存在且合法、变量引用是否有人产出。17 个用例里第 17 个写错，不应该等前 16 个 HTTP 请求跑完才报错。

---

## 3. 一次执行的时序

```
load_suite()
  ├─ 逐文件 yaml.safe_load → _parse_case → Validation(schema 已解析成 dict)
  └─ check_suite()  → 有问题立即抛 CaseLoadError（不发请求）

Runner.run()
  ├─ build_layers(cases)            → list[list[Case]]
  └─ for layer in layers:
       ├─ 检查每个 case 的依赖状态 → 非 PASSED 则 SKIP（带原因）
       ├─ ThreadPoolExecutor(层内并发) 或 串行
       └─ _execute(case):
            for attempt in range(retry+1):
              ctx.render(request)           → 注入 ${...} / ${{...}}
              hook.run_before()
              client.request()             → Response
              ctx.render(expect)            → 上游变量此时才可用
              assertor.run(..., soft)       → 逐条 AssertionResult
              if 5xx 且还有次数 → sleep → continue
              if 全通过 → extract → ctx.set_case(case.id, var, value)
              return CaseResult
  └─ RunResult → write_report() → report.html
```

---

## 4. 已知局限（面试主动说，比被问出来强）

1. **用例依赖本身是双刃剑**：链式依赖会让一个失败带崩一串，且用例不能单独重跑。本项目提供 DAG 是为了编排「业务流程型」用例；单元型接口用例仍应自包含数据。真正的解法是 ADR-1 里 Roadmap 的 `setup/teardown` + 数据池。
2. **没有持久化**：无数据库、无执行历史、无趋势分析，报告是单次快照。
3. **并发模型简单**：只做层内线程池，没有全局调度、没有分布式执行、没有速率限制。
4. **DSL 表达能力有限**：暂不支持参数化矩阵、条件分支、循环、自定义 Python 断言函数（hook 是白名单注册式，刻意不做任意代码执行）。
5. **只覆盖 HTTP/JSON**：没有 gRPC、WebSocket、消息队列、数据库校验。
6. **依赖第三方 JSONPath 实现**：极端表达式的行为受 jsonpath-ng 约束。

---

## 5. 扩展点（面试官问「怎么加功能」时照这个答）

| 想加什么 | 改哪里 | 大约工作量 |
| --- | --- | --- |
| 新断言算子 | `assertor.py` 加一个 `@Assertor.register("xxx")` 函数 | 5 行，loader 自动识别 |
| 新报告格式 | 新建 `report/junit.py`，消费同一个 `RunResult` | 不动执行引擎 |
| 新 hook | `hooks.py` 的 `HookRegistry.register()` | 3 行 |
| 新内置函数 | `context.py` 加 `_fn_xxx()` | 5 行 |
| 新的用例来源（Excel/DB） | 实现一个新的 loader，产出同样的 `Suite` | 其余模块零改动 |
| 参数化矩阵 | loader 展开 `parameters` 成多个 Case（id 加后缀） | 中等 |

这种「加功能只改一个点」的性质，来自模型层与执行层的解耦，是设计部分最值得讲的地方。

---

## 6. 复杂度小结

| 操作 | 复杂度 | 说明 |
| --- | --- | --- |
| DAG 分层 | O(V + E) | Kahn，V=用例数，E=依赖边数 |
| 环路径定位 | O(V + E) | 一次 DFS，带三色标记 |
| 变量渲染 | O(用例字段数) | 递归遍历 + 正则替换 |
| JSONPath 编译 | 缓存 | `@lru_cache(maxsize=256)`，避免重复解析 |
| 报告生成 | O(断言总数) | 字符串拼接，无外部模板引擎 |
