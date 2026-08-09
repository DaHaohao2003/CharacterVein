# 字脉（CharacterVein）

字脉是一个面向汉字演化认知与文化传播的多模态智能体 Web 系统。产品范围见 [PRD](docs/PRD.md)，工程方案见[项目设计文档](docs/PROJECT_DESIGN.md)。

## 环境要求

- Node.js 22+
- pnpm 10+
- Python 3.12
- uv
- Docker Desktop 与 Docker Compose

## 首次安装

```powershell
Copy-Item .env.example .env
pnpm install
uv sync --all-packages
```

`.env` 仅用于本地开发，不要提交。未配置外部模型时，审校会使用可重复的本地实现。

首次启动前生成并核验 4 字演示清单：

```powershell
python scripts/select_jiezi_characters.py
python scripts/verify_jiezi_selection.py
```

清单只包含“云、雷、礼、明”及其 328 张图片。完整 JieZi 下载目录（包括未启用的“风”字原图）仅作为后续数据源，不进入镜像。

## 本地开发

只启动基础设施：

```powershell
docker compose --env-file .env -f infra/compose.yaml up postgres minio minio-init -d
```

分别启动 API 和 Web：

```powershell
pnpm dev:api
pnpm dev:web
```

- Web：http://localhost:3000
- API：http://localhost:8000
- API 文档：http://localhost:8000/docs
- MinIO 控制台：http://localhost:9001

也可以完整容器化启动：

```powershell
pnpm compose:up
```

## 质量检查

```powershell
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test
pnpm build
```

## 数据库迁移

API 容器启动时会自动执行迁移。本地可手动运行：

```powershell
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

## 当前范围

阶段 0 至阶段 7“可信智能体闭环”已经完成。当前支持：

- 从自然语言解析“云、雷、礼、明”四个完整演示案例及受众、时长、阶段数和互动题数量；
- 用户确认结构化任务；
- 使用 PostgreSQL Checkpointer 运行并恢复 LangGraph 工作流；
- 按教育部演化规范展示历史主时间线和草书支线；
- 将 328 张 JieZi 原图写入 MinIO，将图片元数据、检索文本和向量写入 PostgreSQL/pgvector；
- LangGraph 在任务执行中按汉字和七类书体调用图 RAG，从 PostgreSQL/pgvector 召回候选图，优先采用人工标记的代表图，并保留原始路径、署名和许可边界；
- 点击任一历史阶段可展开该汉字、该文体的全部 JieZi 候选图，区分代表字形与异体样本，并可放大或与另一阶段并排观察；
- 首页可直接选择“云、雷、礼、明”进入完整演化流程；异体图库默认展示代表图与少量样本，需要时再展开全部；
- 将 68 条演示文献片段持久化到 PostgreSQL，覆盖四字总览、七类书体的字形/字义语境和教育部演变框架；
- 使用结构化字段、PostgreSQL 全文和 pgvector 向量三路独立召回，并以 RRF 融合且保留通道排名；
- 由 Qwen 生成任务专属九步计划和检索问题，程序锁定真实 LangGraph 节点依赖与工具契约；
- 通过类型化 Tool Registry 记录文献检索、字形检索、来源详情、审校、生成和约束检查的输入、结果、耗时与重试次数；
- 将来源、证据片段、陈述、绑定关系和审校运行分别持久化；
- 使用 `qwen-plus` 输出结构化陈述审校结果，外部模型不可用时明确标记并降级；
- 七个书体阶段和可发布事实均执行陈述级证据绑定；缺少证据时定向回退一次，仍不足则拒绝陈述并请求用户确认资料边界；
- 在工作台展开陈述查看来源定位、证据等级、许可、链接和争议边界；
- 生成讲解、互动题并执行约束检查；
- 查看执行事件并导出 Markdown；
- 上传 JPG、PNG、WEBP、PDF、DOCX、TXT 和 Markdown 材料；
- 将用户原始材料保存到 MinIO，并将资产元数据和提取结果保存到 PostgreSQL；
- 使用 `qwen-vl-ocr` 提取图片中的现代展签文字，在本地解析文档文字；
- 将用户材料与系统检索证据分区存储和展示；
- 只有现代文字明确写出目标字时才自动填入；未知古文字图形必须由用户确认；
- 长任务以后台队列执行，三栏工作台实时查看 Agent 计划、工具调用、三路召回、重试、字形阶段、证据和争议；
- 修改受众、时长、输出形式或互动题数量时复用已审校事实层，不重新检索；
- 将首次生成、局部再生成、人工编辑和历史恢复保存为不可覆盖的内容版本；
- 保存每个内容版本的事实层哈希，便于验证传播层修改没有改变证据与演化知识；
- 复制或导出 Markdown，导出独立 HTML、结构化 JSON，并通过浏览器打印为 PDF。
- 失败或中断任务通过 PostgreSQL Checkpointer 从最近成功节点恢复；
- 通过 20 条黄金查询和正常、证据不足、冲突、恢复场景验证可信智能体闭环；MCP 边界记录在 `docs/MCP_DECISION.md`。

在 `.env` 配置 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY` 后启用真实模型审校；`VLM_PROVIDER` 留空时继承 LLM 提供方，`VLM_BASE_URL` 留空时继承 LLM 地址，默认视觉模型为 `qwen-vl-ocr`。不要提交 `.env`。

Docker Compose 必须通过项目脚本或显式 `--env-file .env` 启动，才能加载仓库根目录的模型配置。本地服务启动后可运行阶段 2 至阶段 5 冒烟检查：

```powershell
uv run --package character-vein-api python apps/api/tests/smoke_stage_two.py
uv run --package character-vein-api python apps/api/tests/smoke_stage_three.py
uv run --package character-vein-api python apps/api/tests/smoke_stage_four.py
uv run --package character-vein-api python apps/api/tests/smoke_stage_five.py
```

发布与恢复方法见 [部署指南](docs/DEPLOYMENT.md)，第三方材料和模型边界见 [来源清单](docs/SOURCES.md)，阶段 7 指标见 [智能体评测规范](docs/STAGE7_EVALUATION.md)，MCP/Skill 边界见 [技术决策](docs/MCP_DECISION.md)，验收数据见 [P0 验收记录](docs/P0_ACCEPTANCE.md)。
