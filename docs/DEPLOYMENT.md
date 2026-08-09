# 字脉部署与恢复指南

## 1. 适用范围

当前部署配置用于本机或受信任内网中的比赛演示。系统尚未实现账号、租户和访问控制，不能把 API、PostgreSQL、MinIO 或 MinIO 控制台直接暴露到公网。

## 2. 启动前检查

- Docker Desktop 已启动并能执行 `docker compose version`；
- 根目录存在未提交的 `.env`，且由 `.env.example` 创建；
- 已替换 PostgreSQL 和 MinIO 的默认开发密码；
- 若启用阿里云百炼，配置 `LLM_PROVIDER=aliyun-bailian`、`LLM_API_KEY`、模型和兼容模式地址；
- `.env`、用户上传文件和数据库备份不得提交到 Git。
- 本地存在 `.data/jiezi/JieZi-Dataset/images`；启动时只按 `data/jiezi/selection.json` 导入 4 字 328 图。

## 3. 启动与验证

```powershell
pnpm compose:up
docker compose --env-file .env -f infra/compose.yaml ps
uv run --package character-vein-api python apps/api/tests/smoke_stage_five.py
```

健康入口：

- Web：<http://localhost:3000>
- API：<http://localhost:8000/api/v1/health>
- API 文档：<http://localhost:8000/docs>

API 容器启动时先执行 Alembic 迁移，再启动 Uvicorn。PostgreSQL 和 MinIO 使用命名卷；普通的容器重建不会删除任务、检查点或上传材料。

`glyph-seed` 是幂等一次性服务：原图写入 MinIO 的 `jiezi-demo/` 前缀，图片元数据和 1024 维检索向量写入 PostgreSQL 的 `glyph_images` 表。重复启动会复用校验和一致的对象，不会把 `.data` 打进任何镜像。可单独重跑：

```powershell
pnpm compose:seed
```

`evidence-seed` 同样幂等，将 68 条比赛演示文献片段写入 PostgreSQL。配置阿里云嵌入后会按每批最多 10 条请求，并在输出中记录 `embedding_provider`、`embedding_requests` 与 `embedding_fallback`；比赛验收要求 `embedding_fallback=false`。可单独重跑：

```powershell
docker compose --env-file .env -f infra/compose.yaml run --rm evidence-seed
```

## 4. 中断与恢复

- 页面刷新：工作台通过 `GET /api/v1/tasks/{task_id}` 重新读取 PostgreSQL 中的任务产物和当前状态；
- 请求断线：重新打开原任务地址。若任务已完成，直接展示持久化结果；
- 节点失败：工作流状态由 PostgreSQL Checkpointer 保存，点击“从最近检查点恢复”，或调用 `POST /api/v1/tasks/{task_id}/resume`；
- API 进程中断：容器恢复后，对仍为 `running` 的任务调用恢复接口；
- 恢复接口只接受 `failed` 或 `running` 状态，避免对已完成任务误生成重复版本；
- 找不到检查点时，恢复接口使用已确认的 `TaskSpec` 安全重跑。

不要用 `docker compose down -v` 处理普通故障；`-v` 会删除数据库和对象存储卷。

## 5. 发布安全边界

- 上传端按允许的扩展名/MIME 白名单处理，并在完整读入内存前限制读取长度；图片 10 MB、文档 20 MB；
- 文件名去除路径并生成任务隔离的对象键；图片由 Pillow 验证；
- 用户材料保存在独立资产区，只作为任务上下文，不自动升级为系统证据；
- 目标字必须由现代文字明确给出或由用户确认；比赛版只执行“云、雷、礼、明”四个已登记案例；
- CORS 只允许 `WEB_ORIGIN`；生产环境必须再增加 HTTPS、身份认证、反向代理限流、恶意文件扫描和密钥托管；
- 日志和导出不得包含 `.env` 或模型 API Key。

## 6. 发布前命令

```powershell
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test
pnpm build
uv run --package character-vein-api python apps/api/tests/smoke_stage_five.py
```

发布记录应保留镜像版本、迁移版本、测试输出、模型名和执行日期。素材和第三方服务边界见 [来源清单](SOURCES.md)，验收结果见 [P0 验收记录](P0_ACCEPTANCE.md)。
