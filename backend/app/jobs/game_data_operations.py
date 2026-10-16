"""Explicit game, MoneyPuck and EDGE registry shared by all entrypoints."""
from .sources.games import operations as game_operations
from .sources.moneypuck import DownloadPolicy, operations as moneypuck_operations
from .sources.edge import EdgePolicy, MetricField, SampleFeed, operation as edge_operation
from .sources.feed_support import missing_player_discovery


def game_data_operations(*, download_policy=DownloadPolicy(), edge_policy=EdgePolicy(), edge_sample_feeds=()):
    return {**game_operations(), **moneypuck_operations(download_policy), "edge": edge_operation(edge_policy, tuple(edge_sample_feeds))}


def source_operations(**core_options):
    """Compose core and game-data jobs; callers can also register them separately."""
    from .core_operations import core_operations
    return {**core_operations(**core_options), **game_data_operations()}
