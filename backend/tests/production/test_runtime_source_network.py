"""External gate G4: the runtime source network opens only in an isolated child with a valid proxy."""
import pytest

from app.services import egress_evidence, source_network
from app.services.outbound_budget import BudgetLimits, BudgetProfile, OutboundBudget
from app.services.outbound_policy import OutboundUnavailableError

PROXY = 'http://127.0.0.1:4750'


@pytest.fixture
def evidence(monkeypatch):
    state = {'isolated': True}
    monkeypatch.setattr(egress_evidence, 'isolated_now', lambda: state['isolated'])
    monkeypatch.setenv(egress_evidence.PROXY_ENV, PROXY)
    return state


def test_closed_without_the_proxy_setting(evidence, monkeypatch):
    monkeypatch.delenv(egress_evidence.PROXY_ENV)
    with pytest.raises(OutboundUnavailableError):
        source_network.make_runtime_source_network()


@pytest.mark.parametrize('proxy', ['', 'http://localhost:4750', 'http://127.0.0.1:4750/', 'socks5://127.0.0.1:1'])
def test_closed_with_an_unacceptable_proxy(evidence, monkeypatch, proxy):
    monkeypatch.setenv(egress_evidence.PROXY_ENV, proxy)
    with pytest.raises(OutboundUnavailableError):
        source_network.make_runtime_source_network()


def test_closed_without_isolation_evidence(evidence):
    evidence['isolated'] = False
    with pytest.raises(OutboundUnavailableError):
        source_network.make_runtime_source_network()


def test_this_unisolated_test_process_never_opens_it(monkeypatch):
    monkeypatch.setenv(egress_evidence.PROXY_ENV, PROXY)  # a proxy alone is not evidence
    with pytest.raises(OutboundUnavailableError):
        source_network.make_runtime_source_network()


def test_opens_through_the_controlled_proxy_with_evidence(evidence):
    network = source_network.make_runtime_source_network()
    assert isinstance(network, source_network.SourceNetworkContext)
    assert network.channel.proxy_url == PROXY and network.channel.readiness_confirmed is True
    assert type(network.budget) is OutboundBudget
    assert network.budget.snapshot().remaining_seconds <= BudgetProfile.download_attempt().seconds


def test_a_supplied_budget_is_used_unchanged(evidence):
    budget = OutboundBudget(BudgetLimits(seconds=5, requests=2))
    assert source_network.make_runtime_source_network(budget).budget is budget


def test_evidence_is_checked_on_every_call(evidence):
    source_network.make_runtime_source_network()
    evidence['isolated'] = False
    with pytest.raises(OutboundUnavailableError):
        source_network.make_runtime_source_network()
