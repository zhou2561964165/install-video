"""Pure budgets are per request; no HTTP or settings dependencies."""
import importlib
import pytest


def retry_api():
    assert importlib.util.find_spec("app.services.summary_retry") is not None
    return importlib.import_module("app.services.summary_retry")


def test_categories_share_a_hard_extra_ceiling_and_instances_are_independent():
    api = retry_api()
    policy = api.RetryPolicy()
    budget = api.RetryBudget(policy)
    assert budget.consume(api.ErrorCategory.FORMAT)
    assert not budget.consume(api.ErrorCategory.FORMAT)
    assert budget.consume(api.ErrorCategory.SEMANTIC)
    assert budget.used == 2
    assert not budget.consume(api.ErrorCategory.SEMANTIC)
    assert api.RetryBudget(policy).used == 0


@pytest.mark.parametrize("category", ["SOURCE", "CAPACITY", "PROVIDER", "NETWORK", "CONFIG"])
def test_terminal_categories_never_consume_budget(category):
    api = retry_api()
    budget = api.RetryBudget(api.RetryPolicy())
    assert not budget.consume(api.ErrorCategory[category])
    assert budget.used == 0


@pytest.mark.parametrize("values", [(True, 1, 2), (1, -1, 2), (1, 1, 3), (1, 1.0, 2)])
def test_invalid_policy_is_rejected(values):
    api = retry_api()
    with pytest.raises(ValueError):
        api.RetryPolicy(*values)


def test_policy_can_disable_retries_and_total_ceiling_wins():
    api = retry_api()
    assert not api.RetryBudget(api.RetryPolicy(0, 0, 0)).consume(api.ErrorCategory.FORMAT)
    budget = api.RetryBudget(api.RetryPolicy(2, 2, 1))
    assert budget.consume(api.ErrorCategory.FORMAT)
    assert not budget.consume(api.ErrorCategory.SEMANTIC)
