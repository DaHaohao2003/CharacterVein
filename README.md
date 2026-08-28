# 字脉（CharacterVein）

字脉是一个可持续对话的多模态汉字文化传播智能体。用户可以像和创作搭档交谈一样，围绕一个汉字提问、研究字形、讨论传播角度，并要求它生成、修改或转换任意形式的传播内容。广播稿、课程活动、公众号文章、展签、触摸屏文案或新的自定义形式都由用户在对话中决定，不受固定模板限制。

系统以真实历代字形、多模态视觉观察、网络搜索和用户上传资料作为生成参考，以减少脱离上下文的编造。Agent 会先识别本轮是回答、探索、创作、修改、转换还是需要澄清，再按需调用资料与字形工具；对话、作品和版本关系均持久化。系统不进行来源等级评定、逐句证据绑定或事实核验。产品范围见 [PRD](docs/PRD.md)，实现架构见[项目设计文档](docs/PROJECT_DESIGN.md)。

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

`.env` 仅用于本地开发，不要提交。未配置外部模型时使用本地模板降级生成。

首次启动前生成并核验 4 字演示清单：

```powershell
python scripts/select_jiezi_characters.py
python scripts/verify_jiezi_selection.py
```

清单只包含“云、雷、礼、明”及其 328 张图片。完整 JieZi 下载目录中的其他原图仅作为后续数据源，不进入镜像、数据库或对象存储演示目录。

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

当前默认主链为：

```text
用户自然语言消息
→ 识别 answer / explore / create / revise / transform / clarify
→ 按需读取最近对话、当前作品、用户资料、网络内容和真实字形
→ 直接回答，或生成用户指定的任意形式完整作品
→ 在后续对话中继续修改或转换
→ 保存消息、作品谱系和不可覆盖版本
→ 中间工作区联动展示字形、参考资料或当前作品
```

三栏工作台是主要交互界面：左侧负责工作区导航，中间展示字形、资料和作品，右侧是持续对话与本轮行动摘要。已有的 Brief、叙事路线和三类传播包流程作为“深度策划模式”保留，但不再是创建内容的必经步骤，也不限制普通对话能生成的内容类型。

当前已实现：

- `qwen3.8-flash` 统一承担对话规划、文本生成和已标注字形图片观察；
- 每轮先输出结构化行动计划，但只展示简明判断、工具动作和完成摘要，不泄露模型私有思维过程；
- 普通问答不会被误触发成作品生成；只有明确创作、修改或转换要求才创建作品；
- 作品类型使用自由文本，不设“只能生成三种内容”的枚举；
- 修改在同一作品谱系上递增版本，转换为新媒介时创建带父作品关系的新谱系；
- PostgreSQL 保存完整对话消息、自由作品、版本、父子关系和工具轨迹，刷新或重启后可以恢复；
- 字形研究按需从 PostgreSQL/MinIO 选取代表图并真正调用多模态模型；面向用户的内容不会出现图片编号、代码点、数据集名称或原始路径；
- 网络搜索和用户上传文档按需进入当前轮上下文，并在界面中作为“本次参考”展示；
- Markdown 作品可以单独导出；旧版整套传播包仍可导出为 Markdown、HTML 或 JSON；
- 旧 LangGraph 深度流程、叙事路线选择、统一母题、三类成品与局部返工作为兼容能力继续可用。

现有 68 条 Stage 7 片段仍保存在 PostgreSQL，但均标记为 `fixture`，只用于回归、离线开发和 20 条黄金查询评测；生产工作流只查询当前任务的 `web` 与 `user_upload` 快照。

### 当前已知边界

- 比赛演示数据库只覆盖“云、雷、礼、明”4 字，不将规划中的 200 字或完整 JieZi 数据集描述为已完成；
- 百炼搜索结果只直接提供标题和 URL；这些记录标为 `metadata_only`，由模型基于搜索结果生成的摘要标为 `partial`，界面不得把摘要称为网页原文；
- 68 条 Stage 7 片段是工程回归/演示夹具，不是生产任务的参考来源；
- 甲骨、金文、战国、篆、隶、楷、草是数据目录的七类书体标签，不代表每个样本都具有精确断代，也不构成无分支的线性传承；
- 图像目录向量来自关联文字元数据，不是视觉编码模型，因此系统不宣称支持以图搜图；
- `qwen3.8-flash` 作为统一多模态主模型，负责任务解析、检索问题规划、内容生成和已标注字形图的可见特征观察；
- 有视觉结果时，正文必须显式展示“多模态字形观察”；即使文本模型忽略提示，程序也会从结构化观察中补入对应书体、图片 ID 和可见特征；
- 当前智能体是单个带条件路由、有限探索循环、人工选择中断和单资产返工子循环的 LangGraph 工作流；不依赖多 Agent、MCP 或 Codex Skill；
- 20 条黄金查询的 Recall@10 = 100% 仅证明当前四字演示语料的回归检索效果，不代表开放汉字或真实用户问题上的泛化准确率；
- 尚未完成文字学专家盲评、用户研究、端到端成本统计和大规模压力测试，这些属于下一轮比赛打磨任务。

在 `.env` 配置 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY` 后启用模型任务解析、检索规划与正文生成；`VLM_PROVIDER` 留空时继承 LLM 提供方，`VLM_BASE_URL` 留空时继承 LLM 地址。默认由 `qwen3.8-flash` 统一承担文本生成、上传图片理解和核心字形视觉观察，`text-embedding-v4` 仍专用于向量检索。不要提交 `.env`。

Docker Compose 必须通过项目脚本或显式 `--env-file .env` 启动，才能加载仓库根目录的模型配置。本地服务启动后可运行阶段 2 至阶段 5 冒烟检查：

```powershell
uv run --package character-vein-api python apps/api/tests/smoke_stage_two.py
uv run --package character-vein-api python apps/api/tests/smoke_stage_three.py
uv run --package character-vein-api python apps/api/tests/smoke_stage_four.py
uv run --package character-vein-api python apps/api/tests/smoke_stage_five.py
```

发布与恢复方法见 [部署指南](docs/DEPLOYMENT.md)，第三方材料和模型边界见 [来源清单](docs/SOURCES.md)，阶段 7 指标见 [智能体评测规范](docs/STAGE7_EVALUATION.md)，MCP/Skill 边界见 [技术决策](docs/MCP_DECISION.md)，验收数据见 [P0 验收记录](docs/P0_ACCEPTANCE.md)。
