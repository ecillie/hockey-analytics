"""Explicit Phase 3 operation registry; imports do not collect or open databases."""
from .sources.contracts import operation as contract_operation
from .sources.nhl import Discovery, MappingCandidate, operations as nhl_operations
from .sources.roster import RosterPolicy, operation as roster_operation
from .sources.transactions import TransactionPolicy, operation as transaction_operation


def core_operations(*, discovery=Discovery(), mappings=(), contract_fallback=True,
                    transaction_policy=TransactionPolicy(), roster_policy=RosterPolicy()):
    """Infrastructure supplies this registry, DataStore, and per-source SourceClient.

    MappingCandidate inputs carry verified cross-ID or manual-decision evidence.
    Phase 4 jobs are deliberately absent and continue to report deferred.
    """
    return {**nhl_operations(discovery=discovery, mappings=tuple(mappings)),
            "contracts": contract_operation(fallback=contract_fallback),
            "transactions": transaction_operation(transaction_policy),
            "roster_reconciliation": roster_operation(roster_policy)}
