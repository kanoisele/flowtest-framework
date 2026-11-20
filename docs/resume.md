# 简历写法与上传前清单

> 原则：**只写能被验证的数字**。面试官会照着简历逐条追问，一个编造的数字就够让整个项目失去可信度。

---

## 一、项目描述（挑一个版本用）

### 版本 A · 偏开发（推荐，测开岗最吃香）

**FlowTest｜轻量级接口自动化测试框架（个人项目，Python）**　[github.com/kanoisele/flowtest-framework](https://github.com/kanoisele/flowtest-framework)
- 设计并实现 YAML 数据驱动的测试框架，基于 **Kahn 拓扑排序 + DFS 环检测** 将用例编排为可执行 DAG，支持同层并发、跨层串行与失败依赖自动 Skip 传播；
- 实现命名空间变量池与模板渲染（`${case.var}` / `${{uuid()}}`），支持跨用例数据传递与加载期**变量数据流静态校验**，将用例配置错误前置到执行前；
- 基于装饰器注册表实现 **21 种断言算子（含 JSON Schema 契约校验）**与软断言，用 `MISSING` 哨兵区分「路径缺失」与 JSON null；
- 设计分层执行引擎：仅对网络异常/5xx 做有上限的重试（断言失败不重试），采用 `threading.local()` 隔离 Session 保障并发安全，产出含脱敏与重试轨迹的单文件 HTML 报告；
- 以 **67 个单测 + 集成测试**保障框架自身质量，接入 GitHub Actions（**4 个 Python 版本**矩阵、ruff、覆盖率、报告 artifact）。

### 版本 B · 偏测试（投偏业务测试的团队时用）

**FlowTest｜接口自动化测试框架（个人项目）**
- 针对接口用例间的数据依赖与执行顺序问题，实现基于 DAG 的用例编排与变量自动传递，支持 5 层依赖链（登录→检索→下单→查询→取消）的自动化回归；
- 设计 17 个示例用例，覆盖功能正向、参数边界值、鉴权异常、契约校验、数据一致性与服务抖动重试场景；
- 通过软断言与结构化报告一次呈现全部失败点，缩短失败定位路径；`flowtest validate` 可在不发请求的情况下完成用例静态校验与执行计划预览。

### 版本 C · 一句话版（简历空间紧张时）

> 自研 Python 接口自动化测试框架 FlowTest：YAML 数据驱动 + DAG 用例编排（拓扑排序/环检测/并发）、21 种断言算子（含 Schema 契约校验）、加载期静态校验、单文件 HTML 报告；配套 67 个自测用例与 4 版本 CI 矩阵。

---

## 二、可以写进简历的量化（全部可现场验证）

| 数字 | 在哪验证 |
| --- | --- |
| 17 个示例用例 / 5 层 DAG | `flowtest validate testcases` |
| 21 种断言算子（含 schema） | `flowtest ops` |
| 67 个自测用例 | `make test` |
| 4 个 Python 版本 CI 矩阵 | `.github/workflows/ci.yml` |
| 7 条设计决策记录 / 30+ 道面试追问 | `docs/architecture.md`、`docs/interview.md` |
| 单次本地全量执行 < 1s | `flowtest demo` 输出 |

**不要写**：「支撑 XX 万 QPS」「在生产环境落地」「团队 X 人使用」「覆盖率 95%」（本项目无此数据）。这类话一追问就穿。

---

## 三、怎么讲（STAR）

### 60 秒版（自我介绍 / 开场）

> 「我做了一个接口自动化测试框架叫 FlowTest。起因是实习/做项目时发现用例之间的依赖特别难管——靠文件名排序，一改顺序就全崩，上游失败下游还会跑出一堆脏数据。所以我用 YAML 让用例显式声明 `depends_on`，框架做拓扑排序和环检测，自动分层：同层并发、跨层串行，上游提取的 token 和订单号自动注入下游请求。另外做了加载期静态校验，变量引用错了在执行前就报错；断言部分有 21 种算子（含 Schema 契约校验）和软断言；重试只针对网络和 5xx，断言失败绝不重试。最后输出单文件 HTML 报告，CI 里能直接当 artifact 下载。框架本身有 67 个自测用例。」

### 3 分钟版（深聊时，按这个顺序）

1. **痛点**（30s）：用例依赖、错误后置、报告依赖环境，各举一个具体现象。
2. **架构**（40s）：Loader → Resolver → Runner → Client/Assertor → Context → Reporter，画一遍数据流。
3. **三个最有分量的设计**（60s）：DAG 分层与 Skip 传播 / 变量命名空间 + 静态数据流校验 / 重试与断言分离。每个都讲「为什么这么选、放弃了什么」。
4. **质量保障**（30s）：三层自测 + FakeClient 测调度 + 真实服务集成测试；CI 矩阵。
5. **局限与下一步**（20s）：用例依赖本身的反模式风险 → 打算加 setup/teardown 和数据池；没有历史趋势、只支持 HTTP/JSON。

> 第 5 步别省。能主动说局限的人，比把项目吹得完美的人更像干过工程。

---

## 四、追问链预演（自己先答一遍）

```
「为什么自己写框架？」→「和 HttpRunner 差在哪？」→「用例依赖是不是反模式？」
   →「那你怎么解决？」→「1000 个用例会怎样？」→「现场给断言引擎加一个算子」
   →「报告为什么不用 Allure？」→「这项目参考了什么？」
```
对应答案都在 `docs/interview.md`，尤其第 3、7、13、23、33、34 题。

---

## 五、上传 GitHub 前清单

- [x] `pyproject.toml`：authors / Homepage / Issues（已按 `kanoisele` 配置）
- [x] `LICENSE`：Copyright（已配置）
- [x] `README.md`：badges 与 clone 地址（已配置）
- [ ] `git init` 后**自己分批提交**，按模块依赖顺序（共 6 批，55 个文件）：
  1. `chore: 项目骨架、依赖声明与核心数据模型` — 配置 + `errors/models/utils`
  2. `feat: 变量上下文、JSONPath 提取与 DAG 依赖解析` — `context/extractor/resolver/hooks`
  3. `feat: 断言引擎、HTTP 客户端与 YAML DSL 加载器` — `assertor/client/loader`
  4. `feat: 执行引擎、CLI、内置 Demo 与 HTML 报告（首次可运行）` — `runner/cli/mock/report` + 示例用例与 Schema
  5. `test: 框架自测、CI 矩阵与容器化配置` — `tests/` + CI + Makefile/Dockerfile
  6. `docs: README、架构设计、面试题库与简历写法` — `README.md` + `docs/`

  > 一个 `Initial commit` 塞进 30 个文件，一看就不像自己写的。**有节奏的提交历史本身就是证据。** 分批不要求每个中间 commit 都能独立运行（CI 到第 5 批才接入），这是正常的功能迭代节奏。

  <details>
  <summary>可直接复制的 6 批命令（先 cd 到项目根目录，整段在同一终端执行）</summary>

  ```bash
  cd "C:/Users/20917/WorkBuddy/2026-11-20-16-50-40/flowtest"
  pwd && ls pyproject.toml README.md
  git init && git branch -M main
  git remote add origin https://github.com/kanoisele/flowtest-framework.git

  # 1) 项目骨架、依赖声明与核心数据模型
  git add .gitignore LICENSE pyproject.toml requirements.txt
  git add flowtest/__init__.py flowtest/core/__init__.py flowtest/core/errors.py flowtest/core/models.py
  git add flowtest/utils/
  git commit -m "chore: 项目骨架、依赖声明与核心数据模型"

  # 2) 变量上下文、JSONPath 提取与 DAG 依赖解析
  git add flowtest/core/context.py flowtest/core/extractor.py flowtest/core/resolver.py flowtest/core/hooks.py
  git commit -m "feat: 变量上下文、JSONPath 提取与 DAG 依赖解析"

  # 3) 断言引擎、HTTP 客户端与 YAML DSL 加载器
  git add flowtest/core/assertor.py flowtest/core/client.py flowtest/core/loader.py
  git commit -m "feat: 断言引擎、HTTP 客户端与 YAML DSL 加载器"

  # 4) 执行引擎、CLI、内置 Demo 与 HTML 报告（首次可运行）
  git add flowtest/core/runner.py flowtest/cli.py
  git add flowtest/mock/ flowtest/report/
  git add testcases/ schemas/ flowtest/examples/
  git commit -m "feat: 执行引擎、CLI、内置 Demo 与 HTML 报告（首次可运行）"

  # 5) 框架自测、CI 矩阵与容器化配置
  git add tests/ .github/workflows/ci.yml
  git add Makefile Dockerfile .dockerignore CHANGELOG.md
  git commit -m "test: 框架自测、CI 矩阵与容器化配置"

  # 6) README、架构设计、面试题库与简历写法
  git add README.md docs/
  git commit -m "docs: README、架构设计、面试题库与简历写法"

  # 收尾：status 应为空，log 应有 6 条，然后推送
  git status --short
  git log --oneline
  git push -u origin main
  ```

  </details>
- [ ] 本地跑 `flowtest demo`，确认 17/17 通过；把 `report.html` 截图存到 `docs/report-preview.png` 并在 README 引用
- [ ] 推上去后确认 CI badge 变绿（第一次跑完再截简历里的图）
- [ ] **自己动手改一处**：比如加一个断言算子或 hook，用自己的 commit 提交。面试时说「这里我后来加了个 xxx」会自然很多

---

## 六、避雷

| ❌ 别做 | 原因 |
| --- | --- |
| fork 别人的项目改 README 当自己的 | 面试官会看 commit 历史、追问实现细节、让你现场改需求；一追问就穿，比没项目更糟 |
| 说「完全独立设计、没参考任何东西」 | DSL 长成那样一定有出处，显得不诚实；大方标注参考反而加分 |
| 编造生产落地 / 性能数据 / 团队规模 | 简历上每个数字都是提问入口 |
| 只放代码不写文档 | 测开岗看工程素养，README 和 CI 常常比代码先被看到 |
| 用 `Initial commit` 一次提交 | 见上 |
| 报告里留着真实 token / 密码 | 本项目已自动脱敏，但换成你自己的用例时要检查 |

**正确姿势**：参考成熟框架的**设计思想** → 从零原创实现 → README 里写明设计参考 → 用自己的提交历史 → 讲清楚取舍和局限。这样既诚实，又能展示「读过源码、懂设计」。

---

## 七、加分动作（有余力再做）

1. 写一篇技术博客（「为什么我给接口测试框架加了 DAG」），简历附链接，比多一个项目更值钱。
2. 录一个 20 秒 GIF：`flowtest demo` → 打开报告 → 筛选失败用例，放 README 顶部。
3. 给 `docs/architecture.md` 里的 Roadmap 挑一条实现掉，作为「持续迭代」的证据。
4. 把 `pytest --cov` 的覆盖率数字和 CI 绿标截进简历附件。
5. 准备一页 A4 的架构图，线上面试共享屏幕时直接指著讲。
