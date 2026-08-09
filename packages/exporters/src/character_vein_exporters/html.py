from html import escape

from character_vein_domain import EvolutionPackage, GeneratedContent


def export_html(content: GeneratedContent, evolution: EvolutionPackage) -> str:
    questions = "".join(f"<li>{escape(item)}</li>" for item in content.interaction_questions)
    sources = "".join(
        "<li>"
        f"<strong>[{escape(item.authority_level)}] {escape(item.title)}</strong> — "
        f"{escape(item.author_or_org)}，{escape(item.locator)}，许可：{escape(item.license)}"
        + (
            f' <a href="{escape(item.url, quote=True)}" rel="noreferrer">来源链接</a>'
            if item.url
            else ""
        )
        + "</li>"
        for item in evolution.evidence
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(content.title)}</title>
  <style>
    body {{ max-width: 860px; margin: 3rem auto; padding: 0 1.5rem; color: #201a17;
      font-family: "Noto Serif SC", "Songti SC", serif; line-height: 1.8; }}
    header {{ border-bottom: 2px solid #9d3f2a; margin-bottom: 2rem; }}
    .meta {{ color: #6f625b; }}
    pre {{ white-space: pre-wrap; font: inherit; }}
    li {{ margin: .55rem 0; }}
    @media print {{ body {{ margin: 0 auto; }} a {{ color: inherit; }} }}
  </style>
</head>
<body>
  <header><h1>{escape(content.title)}</h1>
    <p class="meta">受众：{escape(content.audience)} · 预计 {content.duration_minutes} 分钟</p>
  </header>
  <main><pre>{escape(content.body_markdown)}</pre>
    <h2>互动题</h2><ol>{questions}</ol>
    <h2>来源</h2><ul>{sources}</ul>
  </main>
</body>
</html>
"""
