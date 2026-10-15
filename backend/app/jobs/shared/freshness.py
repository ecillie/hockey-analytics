"""Optional job-specific freshness gates over committed successful producer runs."""
from .configuration import JOBS


def inputs_fresh(context):
    maximum_age = context.config.max_input_age_seconds
    if not maximum_age:
        return True
    from app.jobs.sources.common import scan
    producers = {job for job, spec in JOBS.items()
                 if set(spec.outputs) & set(JOBS[context.config.job].inputs)}
    runs = scan(context, "pipeline_runs")
    for producer in producers:
        for season in range(context.config.first_season, context.config.last_season + 1):
            candidates = [run for run in runs if run.job == producer and run.mode != "validation"
                and run.status in ("succeeded", "no_change") and run.finished_at is not None
                and run.scope.get("first_season", 9999) <= season <= run.scope.get("last_season", 0)
                and set(context.config.game_types) <= set(run.scope.get("game_types", ()))
                and 0 <= (context.run.started_at - run.finished_at).total_seconds() <= maximum_age]
            if not candidates:
                return False
    return True
