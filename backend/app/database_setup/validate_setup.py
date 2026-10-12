"""Final evidence gate; an executor success is not proof of complete source coverage."""
from app.jobs.shared.configuration import JOBS
from app.jobs.shared.coverage import DATASET_POLICIES, CoveragePartition, assess_coverage


def setup_partitions(configurations):
    """Enumerate the coverage baseline from declared work, never from loaded rows."""
    partitions = set()
    for config in configurations:
        for dataset in JOBS[config.job].outputs:
            policy = DATASET_POLICIES.get(dataset)
            if policy is None:
                continue  # Additional logical families still undergo record/relationship checks.
            seasons = range(config.first_season, config.last_season + 1) if policy.history_start else (None,)
            game_types = config.game_types if policy.game_types else (None,)
            for season in seasons:
                for game_type in game_types:
                    partitions.add(CoveragePartition(dataset, season, game_type))
    return tuple(sorted(partitions, key=lambda partition: (partition.dataset, partition.season or 0, partition.game_type or 0)))


def validate_setup(setup_report, requested_partitions, observations, *, current_season, mode="initial"):
    requested_partitions = tuple(requested_partitions)
    if not requested_partitions:
        raise ValueError("Final validation requires an independently declared partition scope")
    if not set(setup_partitions(setup_report.requested)) <= set(requested_partitions):
        raise ValueError("Final validation omitted selected setup partitions")
    coverage = assess_coverage(requested_partitions, observations, current_season=current_season, mode=mode)
    return setup_report.complete and coverage.complete, coverage
