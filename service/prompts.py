"""Versioned task instructions; external context always remains a user message."""
VERSION = 'harpoon-prompts-5'
TASKS = {
    'operations': '''Audit execution only. Prioritize ambiguous orders, missing native protection, fill reconciliation,
stale quotes, late exits, and network/storage errors. Cite supplied evidence IDs, distinguish observations from
hypotheses, and propose a reproducible test for each finding. Return the reference recipe UNCHANGED.
Example: if no campaigns closed, report missing evidence; do not infer a profitable exit rule.''',
    'profitability': '''Optimize realized net capture and capital efficiency at fixed risk. Examine giveback, MFE/MAE,
partial exits, stop costs, holding time, and execution shortfall. exit_layout may be two_targets or single_target; single_target sells TP1 only and preserves an OTO-protected runner without TP2. Horizon never exceeds 72 hours. Portfolio goals and survival simulations never authorize higher risk or leverage. Propose one small exit adjustment with a
falsifiable hypothesis. Preserve reference family, min_rvol, momentum_bps reentry and selection_filter. Do not optimize gross
TP percentages in isolation. Do not infer causation from few trades. Use previous failed_gates, confidence bounds and actual economic costs; do not repeat a rejected parameter set. No invented Sharpe, alpha or expected return.
Example: high MFE followed by a loss can motivate earlier partials, but requires replay and fresh holdout.''',
    'sandbox': '''Propose a materially different but supported entry recipe when evidence justifies testing it.
Supported families are canonical_exit, opening_range, trend_pullback, vwap_reclaim, option_context. The option_context family requires fresh OPRA data for the same underlying and expected range/R >= TP1; proxy or indicative data cannot pass it. Explain the market mechanism,
expected failure regime and counterfactual test in the hypothesis. Keep risk fixed. Compare against the frozen
reference with identical costs and capital. selection_filter may be none or ridge_lcb; fitted weights are never supplied by GPT. trailing_mode may be entry_atr or realized_vol; stagnation_minutes 10-60 and progress_r 0-1. Use supplied XIII book attribution and joint loss evidence; do not call correlated engines independent. If evidence is insufficient, preserve the reference. Annual OOS, purged training, DSR and a fresh prospective holdout remain mandatory. A novel unimplemented indicator cannot be smuggled into the recipe.
Acceptance and transition to PAPER or LIVE belong to external deterministic gates, never to this response.'''
}


def task_prompt(context):
    task = context.get('task', 'profitability') if isinstance(context, dict) else 'invalid'
    if task not in TASKS:
        raise ValueError('Tarea de investigación desconocida')
    return task, TASKS[task]


def enforce_task(result, context):
    task, _ = task_prompt(context)
    reference = context.get('reference')
    if reference is None:  # Legacy protocol has no task-specific reference. Never accepted for new tasks.
        if 'task' in context:
            raise ValueError('Referencia requerida')
        return
    fields = reference.keys() if task == 'operations' else ['family','min_rvol','momentum_bps','reentry','selection_filter'] if task == 'profitability' else []
    if any(result['recipe'].get(k) != reference.get(k, 'none' if k=='selection_filter' else None) for k in fields):
        raise ValueError('La propuesta excede el alcance de la tarea')
