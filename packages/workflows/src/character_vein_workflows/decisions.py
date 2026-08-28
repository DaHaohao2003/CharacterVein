from character_vein_domain import (
    AgentAction,
    AgentDecision,
    AgentDecisionContext,
    AgentPhase,
    ExplorationBudget,
)

PHASE_ACTIONS: dict[AgentPhase, frozenset[AgentAction]] = {
    AgentPhase.MATERIAL_EXPLORATION: frozenset(
        {
            AgentAction.SEARCH_MORE,
            AgentAction.REWRITE_QUERY,
            AgentAction.BUILD_NARRATIVES,
            AgentAction.ASK_USER,
            AgentAction.FINISH,
        }
    ),
    AgentPhase.GLYPH_EXPLORATION: frozenset(
        {
            AgentAction.RESELECT_GLYPH,
            AgentAction.BUILD_NARRATIVES,
            AgentAction.ASK_USER,
            AgentAction.FINISH,
        }
    ),
    AgentPhase.NARRATIVE_BUILD: frozenset(
        {AgentAction.BUILD_NARRATIVES, AgentAction.ASK_USER, AgentAction.FINISH}
    ),
    AgentPhase.ASSET_EVALUATION: frozenset(
        {
            AgentAction.SEARCH_MORE,
            AgentAction.RESELECT_GLYPH,
            AgentAction.REWRITE_ASSET,
            AgentAction.ASK_USER,
            AgentAction.FINISH,
        }
    ),
}


def allowed_actions(
    context: AgentDecisionContext,
    budget: ExplorationBudget,
) -> list[AgentAction]:
    return [
        action
        for action in AgentAction
        if action in PHASE_ACTIONS[context.phase] and budget.can_execute(action)
    ]


def accept_decision(
    decision: AgentDecision,
    context: AgentDecisionContext,
    budget: ExplorationBudget,
) -> ExplorationBudget:
    permitted = allowed_actions(context, budget)
    if decision.action not in permitted:
        choices = "、".join(item.value for item in permitted)
        raise ValueError(
            f"阶段 {context.phase.value} 不允许动作 {decision.action.value}；可用动作：{choices}"
        )
    return budget.consume(decision.action)
