import hashlib
from pathlib import PurePosixPath

from character_vein_domain import (
    Claim,
    ClaimType,
    Evidence,
    EvolutionPackage,
    GlyphAvailability,
    GlyphStage,
    Source,
)
from character_vein_workflows.jiezi_catalog import catalog_entry

JIEZI_URL = "https://huggingface.co/datasets/Ran0/JieZi"
JIEZI_LICENSE = "CC BY-NC-ND 4.0; non-commercial research only"
JIEZI_ATTRIBUTION = (
    "字形图：JieZi-Dataset（DLVC-Lab, South China University of Technology）；"
    "原始资料版权归原提供方，图像集合致谢 MegaHan97K"
)
MOE_EVOLUTION_URL = (
    "https://www.moe.gov.cn/jyb_xwfb/xw_fbh/moe_2069/s7135/s7562/s7569/"
    "201308/t20130827_156347.html"
)
MOE_SOURCE_ID = "source-moe-hanzi-evolution"

FRAMEWORK_CHUNKS = (
    (
        "periodization",
        "历史分期",
        "教育部文章以秦国篆隶变化为古文字与今文字的分水岭：商代、西周春秋、"
        "战国和秦系材料属于古文字研究范围，隶书、楷书构成今文字主干。",
        ["古文字", "今文字", "篆隶", "分期"],
    ),
    (
        "oracle",
        "甲骨材料",
        "大规模、成系统的甲骨文字材料主要见于商代晚期；资料类型与精确年代应分开记录，"
        "不能只凭“甲骨文”标签推断每张图的具体年代。",
        ["甲骨文", "商代晚期", "资料类型", "年代"],
    ),
    (
        "bronze",
        "金文材料",
        "金文材料跨越商周，西周和春秋时期持续变化并具有地域书写特色，因此金文不等同于"
        "单一朝代或单一规范字形。",
        ["金文", "商周", "西周", "春秋", "地域"],
    ),
    (
        "warring-states",
        "战国文字",
        "战国文字存在明显地域差异，至少需要区分六国文字与秦系文字；来源没有地域依据时"
        "应标为地域未详，而不是猜测所属系统。",
        ["战国文字", "六国文字", "秦系文字", "地域未详"],
    ),
    (
        "seal-clerical",
        "篆隶过渡",
        "秦统一后以小篆作为统一文字标准，实际书写中的方折化和结构改造形成秦隶，"
        "篆隶变化是古文字向今文字过渡的重要节点。",
        ["小篆", "秦隶", "规范化", "古今文字"],
    ),
    (
        "clerical-cursive",
        "隶书与草书",
        "秦隶发展为汉隶，隶书成为两汉主要通行字体；草书主要承担起草、通信等快速书写功能，"
        "应作为并行书写支线，而不是楷书之后的线性终点。",
        ["秦隶", "汉隶", "草书", "书写支线"],
    ),
    (
        "running-regular",
        "行书与楷书",
        "东汉晚期行书在隶书和草书基础上形成，汉魏之际楷书逐步产生并在魏晋时期取得主导地位；"
        "书体之间存在并行和交互，不能画成无分支的七段直线。",
        ["行书", "楷书", "汉魏", "魏晋", "并行"],
    ),
    (
        "principles",
        "演变规律",
        "汉字形体演变可从简化、声化和规范化三类一般规律观察，但一般规律不能直接替代"
        "具体单字证据，单字结论仍须绑定可定位材料。",
        ["简化", "声化", "规范化", "单字证据"],
    ),
)

STAGE_CHANGE_NOTES = {
    "金文": "与甲骨材料对读时，需关注载体、线条和构件布局差异，不能假定所有异体沿单线演变。",
    "战国文字": "战国文字存在地域差异；JieZi 未提供地域系统时统一标为“地域未详”。",
    "篆书": "篆书样本体现线条与结构整理；来源未细分时不直接称为秦小篆。",
    "隶书": "隶变使笔势趋向方折和平直；来源未细分时不直接断定为秦隶或汉隶。",
    "楷书": "楷书阶段结构进一步稳定，成为后世规范书写主干。",
    "草书": "草书属于快速书写与书法支线，不是楷书之后的下一代规范字形。",
}

DEMO_CASES = {
    "云": {
        "slug": "cloud",
        "theme": "天象观察、构形与文化意象",
        "context": "“云”连接天象观察与后世文化意象，但字形事实和文学联想需要分开说明。",
    },
    "雷": {
        "slug": "thunder",
        "theme": "自然认知、构形与声音想象",
        "context": "“雷”的历代字形可用于讨论自然认知，不能仅凭图形联想代替文字材料。",
    },
    "礼": {
        "slug": "ritual",
        "theme": "礼仪实践、字义与社会秩序",
        "context": "“礼”的文化意义需要结合具体时代、用例与礼仪实践，不能概括成恒定不变的单一观念。",
    },
    "明": {
        "slug": "bright",
        "theme": "光明、构形与认知引申",
        "context": "“明”可展示字形构件与光亮、清楚等语义之间的长期联系及引申。",
    },
}
SUPPORTED_DEMO_CHARACTERS = tuple(DEMO_CASES)


def _demo_slug(character: str) -> str:
    return DEMO_CASES[character]["slug"]


def _jiezi_source(character: str, slug: str) -> Source:
    entry = catalog_entry(character)
    available = [stage.script_type for stage in entry.stages if stage.availability == "available"]
    missing = [stage.script_type for stage in entry.stages if stage.availability == "dataset_gap"]
    locator = (
        f"{entry.codepoint}；已收录：{'、'.join(available)}；"
        f"数据缺口：{'、'.join(missing) if missing else '无'}"
    )
    return Source(
        source_id=f"source-jiezi-{slug}",
        source_type="expert_audited_glyph_dataset",
        title=f"JieZi-Dataset·{character}",
        author_or_org="DLVC-Lab / South China University of Technology",
        publication_date="2026",
        locator=locator,
        url=JIEZI_URL,
        authority_level="B",
        license=JIEZI_LICENSE,
    )


def _jiezi_stages(character: str, slug: str) -> list[GlyphStage]:
    entry = catalog_entry(character)
    stages: list[GlyphStage] = []
    for index, catalog_stage in enumerate(entry.stages):
        available = catalog_stage.availability == GlyphAvailability.AVAILABLE
        source_path = catalog_stage.representative_source_path if available else None
        image_url = None
        image_id = None
        if source_path:
            relative = source_path.removeprefix("JieZi-Dataset/images/")
            image_url = f"/backend/api/v1/glyph-images/{relative}"
            image_id = str(PurePosixPath(relative).with_suffix(""))
        description = catalog_stage.special_structure or (
            f"JieZi 元数据将该字标为“{catalog_stage.structure}”结构。"
            if catalog_stage.structure
            else "JieZi 提供该书体的代表样本，未给出更细的单图结构说明。"
        )
        if not available:
            description = f"JieZi 精选目录中暂无“{character}”的{catalog_stage.script_type}样本。"
        stages.append(
            GlyphStage(
                stage_id=f"{slug}-{catalog_stage.script_code.lower()}",
                character=character,
                script_type=catalog_stage.script_type,
                script_code=catalog_stage.script_code,
                period=catalog_stage.historical_period,
                approximate_date="数据集未提供该图精确年代",
                historical_period=catalog_stage.historical_period,
                lineage_role=catalog_stage.lineage_role,
                region_or_system=catalog_stage.region_or_system,
                sample_date=None,
                image_url=image_url,
                image_id=image_id,
                source_id=f"source-jiezi-{slug}",
                source_label=(
                    f"JieZi-Dataset·{catalog_stage.script_type}·{image_id}"
                    if image_id
                    else f"JieZi-Dataset·{catalog_stage.script_type}·暂无样本"
                ),
                source_path=source_path,
                image_attribution=JIEZI_ATTRIBUTION if available else None,
                availability=catalog_stage.availability,
                variant_type="representative" if available else "dataset_gap",
                structure_description=description,
                change_from_previous=(
                    STAGE_CHANGE_NOTES.get(catalog_stage.script_type) if index else None
                ),
            )
        )
    return stages


def _catalog_evidence(character: str) -> Evidence:
    entry = catalog_entry(character)
    metadata_stage = next(
        stage for stage in entry.stages if stage.original_meaning or stage.evolution
    )
    summary_parts = []
    if metadata_stage.original_meaning:
        summary_parts.append(f"本义说明：{metadata_stage.original_meaning}")
    if metadata_stage.evolution:
        summary_parts.append(f"字形演变说明：{metadata_stage.evolution}")
    slug = _demo_slug(character)
    content = "；".join(summary_parts)
    return Evidence(
        evidence_id=f"evidence-jiezi-{slug}",
        source_id=f"source-jiezi-{slug}",
        source_type="expert_audited_glyph_dataset",
        title=f"JieZi-Dataset·{character}元数据",
        author_or_org="DLVC-Lab / South China University of Technology",
        publication_date="2026",
        quote_or_summary=content,
        locator=f"{entry.codepoint}；甲骨、金文、战国、篆、隶、楷、草七类元数据与图像",
        url=JIEZI_URL,
        authority_level="B",
        license=JIEZI_LICENSE,
        keywords=[character, "甲骨文", "金文", "战国文字", "篆书", "隶书", "楷书", "草书"],
        metadata={"character": character, "kind": "glyph_dataset"},
        character=character,
        topic="overview",
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _catalog_stage_evidence(character: str) -> list[Evidence]:
    entry = catalog_entry(character)
    slug = _demo_slug(character)
    evidence: list[Evidence] = []
    for index, stage in enumerate(entry.stages):
        if stage.availability != GlyphAvailability.AVAILABLE:
            continue
        structure = stage.special_structure or stage.structure or "数据集未给出细分结构"
        shape_content = (
            f"{character}·{stage.script_type}：JieZi 元数据记录结构为“{structure}”。"
            f"{stage.evolution or '数据集未提供该分类的单独演变摘要。'}"
        )
        context_content = (
            f"{character}·{stage.script_type}目录记录：历史范围为{stage.historical_period}，"
            f"谱系角色为{stage.lineage_role.value}，地域或系统为"
            f"{stage.region_or_system or '未详'}；本义字段为"
            f"{stage.original_meaning or '未提供'}。目录分类不能替代单图精确断代。"
        )
        keywords = list(
            dict.fromkeys(
                [
                    character,
                    stage.script_type,
                    stage.historical_period,
                    stage.region_or_system or "地域未详",
                    stage.structure,
                    stage.special_structure,
                ]
            )
        )
        evidence.append(
            Evidence(
                evidence_id=f"evidence-jiezi-{slug}-{stage.script_code.lower()}-shape",
                source_id=f"source-jiezi-{slug}",
                source_type="expert_audited_glyph_dataset",
                title=f"JieZi-Dataset·{character}·{stage.script_type}",
                author_or_org="DLVC-Lab / South China University of Technology",
                publication_date="2026",
                quote_or_summary=shape_content,
                locator=f"{stage.metadata_path or entry.codepoint}；结构与演变字段",
                url=JIEZI_URL,
                authority_level="B",
                license=JIEZI_LICENSE,
                keywords=[*keywords, "构形", "演变"],
                metadata={"kind": "glyph_stage", "script_code": stage.script_code},
                character=character,
                script_type=stage.script_type,
                historical_period=stage.historical_period,
                topic="shape",
                chunk_index=index * 2,
                content_hash=hashlib.sha256(shape_content.encode("utf-8")).hexdigest(),
            )
        )
        evidence.append(
            Evidence(
                evidence_id=f"evidence-jiezi-{slug}-{stage.script_code.lower()}-context",
                source_id=f"source-jiezi-{slug}",
                source_type="expert_audited_glyph_dataset",
                title=f"JieZi-Dataset·{character}·{stage.script_type}",
                author_or_org="DLVC-Lab / South China University of Technology",
                publication_date="2026",
                quote_or_summary=context_content,
                locator=f"{stage.metadata_path or entry.codepoint}；分期、本义与来源边界字段",
                url=JIEZI_URL,
                authority_level="B",
                license=JIEZI_LICENSE,
                keywords=[*keywords, "本义", "分期", "资料边界"],
                metadata={"kind": "glyph_context", "script_code": stage.script_code},
                character=character,
                script_type=stage.script_type,
                historical_period=stage.historical_period,
                topic="meaning_context",
                chunk_index=index * 2 + 1,
                content_hash=hashlib.sha256(context_content.encode("utf-8")).hexdigest(),
            )
        )
    return evidence


def _moe_source() -> Source:
    return Source(
        source_id=MOE_SOURCE_ID,
        source_type="official_policy_article",
        title="古今汉字的演变",
        author_or_org="陈双新、李娜 / 中华人民共和国教育部",
        publication_date="2013-08-27",
        locator="教育部政府门户网站；汉字演变专题",
        url=MOE_EVOLUTION_URL,
        authority_level="A",
        license="官方公开网页；仅保存工程化摘要，引用须注明教育部原文",
    )


def _framework_evidence() -> list[Evidence]:
    return [
        Evidence(
            evidence_id=f"evidence-moe-framework-{chunk_id}",
            source_id=MOE_SOURCE_ID,
            source_type="official_policy_article",
            title="古今汉字的演变",
            author_or_org="陈双新、李娜 / 中华人民共和国教育部",
            publication_date="2013-08-27",
            quote_or_summary=content,
            locator=f"教育部《古今汉字的演变》；{topic}",
            url=MOE_EVOLUTION_URL,
            authority_level="A",
            license="官方公开网页；仅保存工程化摘要，引用须注明教育部原文",
            keywords=keywords,
            metadata={"kind": "evolution_framework", "scope": "global"},
            topic="framework",
            chunk_index=index,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )
        for index, (chunk_id, topic, content, keywords) in enumerate(FRAMEWORK_CHUNKS)
    ]


def _catalog_evolution_package(character: str) -> EvolutionPackage:
    case = DEMO_CASES[character]
    slug = case["slug"]
    entry = catalog_entry(character)
    evidence = _catalog_evidence(character)
    stage_evidence = _catalog_stage_evidence(character)
    framework_evidence = _framework_evidence()
    framework_by_id = {item.evidence_id: item for item in framework_evidence}
    original_meanings = list(
        dict.fromkeys(stage.original_meaning for stage in entry.stages if stage.original_meaning)
    )
    claims = [
        Claim(
            claim_id=f"claim-{slug}-dataset",
            content=(
                f"JieZi 元数据把“{character}”的本义概括为：{original_meanings[0]}"
                if original_meanings
                else f"JieZi 为“{character}”收录了七类历史字形样本。"
            ),
            claim_type=ClaimType.LITERATURE_FACT,
            evidence_ids=[evidence.evidence_id],
            evidence_grade="B",
        ),
        Claim(
            claim_id=f"claim-{slug}-coverage",
            content=(
                f"当前演示语料为“{character}”登记了 "
                f"{entry.available_script_count} 类书体、{entry.total_image_count} 个真实异体样本。"
            ),
            claim_type=ClaimType.LITERATURE_FACT,
            evidence_ids=[evidence.evidence_id],
            evidence_grade="B",
        ),
        Claim(
            claim_id=f"claim-{slug}-lineage",
            content="展示以早期文字、篆隶变化和楷书规范形为主时间线，并把草书作为书写演化支线。",
            claim_type=ClaimType.MAINSTREAM_INTERPRETATION,
            evidence_ids=[
                "evidence-moe-framework-clerical-cursive",
                "evidence-moe-framework-running-regular",
            ],
            evidence_grade="A",
        ),
        Claim(
            claim_id=f"claim-{slug}-boundary",
            content="数据集分类用于组织代表样本，不等于每个样本都具备精确断代，也不构成无分支的七阶段直线。",
            claim_type=ClaimType.SYSTEM_SYNTHESIS,
            evidence_ids=[
                evidence.evidence_id,
                "evidence-moe-framework-periodization",
                "evidence-moe-framework-principles",
            ],
            evidence_grade="B",
        ),
    ]
    stage_evidence_by_id = {item.evidence_id: item for item in stage_evidence}
    claims.extend(
        Claim(
            claim_id=f"claim-{slug}-{stage.script_code.lower()}-shape",
            content=(
                f"JieZi 元数据将“{character}”的{stage.script_type}样本结构记录为“"
                f"{stage.special_structure or stage.structure or '未细分'}”，目录历史范围标为"
                f"“{stage.historical_period}”；目录分类不替代单图精确断代。"
            ),
            claim_type=ClaimType.LITERATURE_FACT,
            evidence_ids=[
                f"evidence-jiezi-{slug}-{stage.script_code.lower()}-shape",
                f"evidence-jiezi-{slug}-{stage.script_code.lower()}-context",
            ],
            evidence_grade="B",
        )
        for stage in entry.stages
        if stage.availability == GlyphAvailability.AVAILABLE
    )
    return EvolutionPackage(
        character=character,
        sources=[_jiezi_source(character, slug), _moe_source()],
        glyph_stages=_jiezi_stages(character, slug),
        shape_changes=[
            "比较甲骨、金文与战国材料中的构件和布局差异",
            "观察篆书整理与隶变带来的线条、笔势和结构变化",
            "以楷书作为规范主干，并把草书作为快速书写支线",
        ],
        meaning_changes=original_meanings or ["JieZi 元数据未提供统一的本义说明"],
        cultural_contexts=[case["context"], "展示中的每个字形都保留 JieZi 原始路径，方便回查。"],
        claims=claims,
        evidence=[
            evidence,
            *stage_evidence_by_id.values(),
            framework_by_id["evidence-moe-framework-clerical-cursive"],
            framework_by_id["evidence-moe-framework-running-regular"],
            framework_by_id["evidence-moe-framework-periodization"],
            framework_by_id["evidence-moe-framework-principles"],
        ],
        controversies=["JieZi 的七类目录是数据集分类，不能直接当作严格年代分期。"],
        audit_summary={"approved_claims": 0, "rejected_claims": 0, "status": "pending"},
    )


def case_sources(character: str) -> list[Source]:
    if character in DEMO_CASES:
        return [_jiezi_source(character, _demo_slug(character)), _moe_source()]
    raise ValueError(f"尚未登记演示字：{character}")


def case_evidence_corpus(character: str) -> list[Evidence]:
    if character in DEMO_CASES:
        return [
            _catalog_evidence(character),
            *_catalog_stage_evidence(character),
            *_framework_evidence(),
        ]
    raise ValueError(f"尚未登记演示字：{character}")


def case_evolution_package(character: str) -> EvolutionPackage:
    if character in DEMO_CASES:
        return _catalog_evolution_package(character)
    raise ValueError(f"尚未登记演示字：{character}")


def all_demo_sources() -> list[Source]:
    return list(
        {
            source.source_id: source
            for character in SUPPORTED_DEMO_CHARACTERS
            for source in case_sources(character)
        }.values()
    )


def all_demo_evidence_corpus() -> list[Evidence]:
    return list(
        {
            evidence.evidence_id: evidence
            for character in SUPPORTED_DEMO_CHARACTERS
            for evidence in case_evidence_corpus(character)
        }.values()
    )
