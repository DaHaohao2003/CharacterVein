# 演示汉字历史字形素材来源

演示工作台不再使用本目录中的自制 SVG。原始 JPG/PNG 由导入任务写入 MinIO，图片元数据、检索文本和向量写入 PostgreSQL/pgvector，页面通过 `/backend/api/v1/glyph-images/{codepoint}/{script}/{file}` 读取。

- 项目主页：[Ran00w/JieZi](https://github.com/Ran00w/JieZi)
- 数据下载：[Ran0/JieZi](https://huggingface.co/datasets/Ran0/JieZi)
- 许可：CC BY-NC-ND 4.0，仅限非商业研究使用
- 本地归档：`.data/jiezi/JieZi-Dataset/images`（不进入 Git 和 Docker 构建上下文）
- 系统清单：`data/jiezi/selection.json`
- 完整性报告：`data/jiezi/import_report.json`

当前演示集只包含“云、雷、礼、明”4 个汉字，共 328 张原图；4 字均覆盖甲骨、金文、战国、篆、隶、楷、草七类。其他已下载图片只作为后续扩充源，不进入 Docker 镜像、PostgreSQL 或 MinIO 演示目录。每张图在 API 数据中保留原始数据集路径。原始资料版权仍归各提供方，JieZi 项目对图像集合致谢 MegaHan97K 等来源。
