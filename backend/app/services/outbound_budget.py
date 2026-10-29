"""In-process, monotonic, atomic hierarchical outbound accounting.

No network/DB I/O. Callers must acquire a response before sending each request,
charge raw input before decoding, and bound decoder output using the remaining
decoded allowance. This counter cannot stop a socket, decompressor or process;
adapters must close streams and the execution supervisor enforces hard timeouts.
"""

from dataclasses import dataclass, field
from contextlib import contextmanager
from enum import Enum
import math
import threading
import time
from typing import Callable

from .outbound_policy import OutboundError, OutboundPurpose


def _clock_sample(clock):
    """Discard a callable's exception before constructing a safe error."""
    try:
        value = clock()
        if type(value) in (int, float) and math.isfinite(value):
            return value
    except Exception:
        pass
    return None


class BudgetReason(str, Enum):
    DEADLINE = 'deadline'
    REQUESTS = 'requests'
    REDIRECTS = 'redirects'
    RAW_BYTES = 'raw_bytes'
    DECODED_BYTES = 'decoded_bytes'
    RESPONSE_RAW_BYTES = 'response_raw_bytes'
    RESPONSE_DECODED_BYTES = 'response_decoded_bytes'
    CHILDREN = 'children'
    CLOSED = 'closed'


class OutboundBudgetError(OutboundError):
    def __init__(self, reason: BudgetReason, purpose: OutboundPurpose = OutboundPurpose.METADATA):
        if not isinstance(reason, BudgetReason):
            raise ValueError('Invalid outbound error classification') from None
        if reason is BudgetReason.DEADLINE:
            code = 'source_timeout'
        elif reason in (BudgetReason.RAW_BYTES, BudgetReason.DECODED_BYTES, BudgetReason.RESPONSE_RAW_BYTES, BudgetReason.RESPONSE_DECODED_BYTES):
            code = 'subtitle_too_large' if purpose == OutboundPurpose.SUBTITLE else 'source_too_large'
        else:
            code = 'source_budget_exhausted'
        super().__init__(code, reason.value)


@dataclass(frozen=True)
class BudgetLimits:
    seconds: float = 30.0
    requests: int = 64
    redirects: int = 5
    raw_bytes: int = 16 * 1024 * 1024
    decoded_bytes: int = 16 * 1024 * 1024
    response_raw_bytes: int = 8 * 1024 * 1024
    response_decoded_bytes: int = 8 * 1024 * 1024
    children: int = 0

    def __post_init__(self):
        try:
            if isinstance(self.seconds, bool) or not math.isfinite(self.seconds) or self.seconds <= 0:
                raise ValueError
            for value in (self.requests, self.raw_bytes, self.decoded_bytes, self.response_raw_bytes, self.response_decoded_bytes):
                if type(value) is not int or value <= 0:
                    raise ValueError
            for value in (self.redirects, self.children):
                if type(value) is not int or value < 0:
                    raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Invalid outbound budget configuration') from None


class BudgetProfile:
    """Approved new-mode defaults; no existing runtime configuration is changed.

    Platform adapters still apply their tighter original limits. Provider calls
    need independent explicitly reviewed limits; they do not borrow source scope.
    """

    @staticmethod
    def resolve() -> BudgetLimits:
        return BudgetLimits()

    @staticmethod
    def direct_parent() -> BudgetLimits:
        return BudgetLimits(seconds=60, requests=128, raw_bytes=32 * 1024 * 1024,
                            decoded_bytes=32 * 1024 * 1024, children=2)

    @staticmethod
    def subtitle() -> BudgetLimits:
        return BudgetLimits(response_raw_bytes=5 * 1024 * 1024,
                            response_decoded_bytes=5 * 1024 * 1024)

    @staticmethod
    def download_attempt() -> BudgetLimits:
        size = 2 * 1024 * 1024 * 1024
        return BudgetLimits(seconds=1800, requests=1024, raw_bytes=size,
                            decoded_bytes=size, response_raw_bytes=size,
                            response_decoded_bytes=size)

    @staticmethod
    def download_parent() -> BudgetLimits:
        size = 2 * 1024 * 1024 * 1024
        return BudgetLimits(seconds=1800, requests=3 * 1024, raw_bytes=3 * size,
                            decoded_bytes=3 * size, response_raw_bytes=size,
                            response_decoded_bytes=size, children=3)


@dataclass(frozen=True)
class RequestLimits:
    """Transient, tightening-only HTTP limits; never a durable child budget."""

    seconds: float | None = None
    response_raw_bytes: int | None = None
    response_decoded_bytes: int | None = None

    def __post_init__(self):
        try:
            if self.seconds is not None and (
                isinstance(self.seconds, bool) or not isinstance(self.seconds, (int, float))
                or not math.isfinite(self.seconds) or self.seconds <= 0
            ):
                raise ValueError
            if any(value is not None and (type(value) is not int or value <= 0)
                   for value in (self.response_raw_bytes, self.response_decoded_bytes)):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Invalid outbound request limits') from None


@dataclass(frozen=True)
class BudgetSnapshot:
    requests: int
    redirects: int
    raw_bytes: int
    decoded_bytes: int
    children: int
    remaining_seconds: float


@dataclass(frozen=True)
class BudgetCheckpoint:
    """Trusted persistence DTO, not user input and not a durable store itself.

    Persist the entire root atomically and fence its former executor before
    restore. elapsed_seconds must come from the authoritative persistent task
    deadline/clock, including downtime; unknown elapsed time must not be zeroed.
    Absolute monotonic values cannot be copied across processes/boots.
    """

    limits: BudgetLimits
    purpose: OutboundPurpose
    remaining_seconds: float
    requests: int
    redirects: int
    raw_bytes: int
    decoded_bytes: int
    blocked: BudgetReason | None
    children: tuple['BudgetCheckpoint', ...] = ()


class OutboundBudget:
    def __init__(
        self, limits: BudgetLimits, *, purpose: OutboundPurpose | str = OutboundPurpose.METADATA,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not isinstance(limits, BudgetLimits):
            raise ValueError('Invalid outbound budget configuration') from None
        try:
            self._purpose = OutboundPurpose(purpose)
        except (TypeError, ValueError):
            raise ValueError('Invalid outbound purpose') from None
        self._limits = limits
        self._clock = clock
        now = _clock_sample(clock)
        if now is None:
            raise ValueError('Invalid outbound budget clock') from None
        self._started = now
        self._last_now = now
        self._deadline = now + limits.seconds
        if not math.isfinite(self._deadline):
            raise ValueError('Invalid outbound budget clock') from None
        self._lock = threading.RLock()
        self._parent: OutboundBudget | None = None
        self._requests = self._redirects = self._raw_bytes = self._decoded_bytes = 0
        self._children: list[OutboundBudget] = []
        self._blocked: BudgetReason | None = None

    def _now(self) -> float:
        root = self._chain()[-1]
        with root._lock:
            value = _clock_sample(self._clock)
            if value is None or value < root._last_now:
                raise ValueError('Invalid outbound budget clock') from None
            root._last_now = value
            return value

    def _attach(self, parent: 'OutboundBudget') -> None:
        """Publish a constructed child only after validating its sampled time."""
        root = parent._chain()[-1]
        with root._lock:
            if self._last_now < root._last_now:
                raise ValueError('Invalid outbound budget clock') from None
            root._last_now = self._last_now
            self._parent, self._lock = parent, parent._lock
            self._deadline = min(self._deadline, parent._deadline)

    def _chain(self) -> list['OutboundBudget']:
        chain = []
        node: OutboundBudget | None = self
        while node is not None:
            chain.append(node)
            node = node._parent
        return chain

    def _check(self) -> list['OutboundBudget']:
        chain = self._chain()
        now = self._now()
        for node in chain:
            if node._blocked is not None:
                raise OutboundBudgetError(node._blocked, self._purpose) from None
            if now >= node._deadline:
                node._blocked = BudgetReason.DEADLINE
                raise OutboundBudgetError(BudgetReason.DEADLINE, self._purpose) from None
        return chain

    def child(self, limits: BudgetLimits, *, purpose: OutboundPurpose | str | None = None) -> 'OutboundBudget':
        """Create one counted resolve/attempt; inherits root lock and deadline."""
        with self._lock:
            self._check()
            if len(self._children) >= self._limits.children:
                raise OutboundBudgetError(BudgetReason.CHILDREN, self._purpose) from None
            child = OutboundBudget(limits, purpose=self._purpose if purpose is None else purpose, clock=self._clock)
            child._attach(self)
            self._children.append(child)
            return child

    def resume_child(self, index: int) -> 'OutboundBudget':
        """Return the existing branch after recovery; never create a new budget."""
        with self._lock:
            if type(index) is not int or not 0 <= index < len(self._children):
                raise ValueError('Invalid outbound budget child') from None
            return self._children[index]

    def remaining_seconds(self) -> float:
        with self._lock:
            self._check()
            return max(0.0, min(node._deadline for node in self._chain()) - self._now())

    def request_scope(self, limits: RequestLimits = RequestLimits(), *,
                      purpose: OutboundPurpose | str | None = None) -> 'OutboundRequestScope':
        """Borrow this counter tree for one HTTP call, including all redirects.

        The scope has no independent counters and consumes no child slot. It
        cannot be checkpointed/resumed as another resolve or download attempt.
        """
        return OutboundRequestScope(self, limits, purpose=purpose)

    def begin_request(self, *, redirect: bool = False,
                      response_raw_bytes: int | None = None,
                      response_decoded_bytes: int | None = None,
                      purpose: OutboundPurpose | str | None = None) -> 'OutboundResponseBudget':
        """Charge before each HTTP send, including retries, manifests and keys.

        redirect=True charges both one HTTP request and one redirect hop. Only
        call this after validating Location and before following it.
        """
        if type(redirect) is not bool:
            raise ValueError('Invalid outbound budget charge') from None
        limits = RequestLimits(response_raw_bytes=response_raw_bytes,
                               response_decoded_bytes=response_decoded_bytes)
        try:
            purpose = self._purpose if purpose is None else OutboundPurpose(purpose)
        except (TypeError, ValueError):
            raise ValueError('Invalid outbound purpose') from None
        with self._lock:
            chain = self._check()
            for node in chain:
                if node._requests >= node._limits.requests:
                    node._blocked = BudgetReason.REQUESTS
                    raise OutboundBudgetError(BudgetReason.REQUESTS, self._purpose) from None
                if redirect and node._redirects >= node._limits.redirects:
                    node._blocked = BudgetReason.REDIRECTS
                    raise OutboundBudgetError(BudgetReason.REDIRECTS, self._purpose) from None
            for node in chain:
                node._requests += 1
                node._redirects += int(redirect)
            return OutboundResponseBudget(self, limits=limits, purpose=purpose)

    def snapshot(self) -> BudgetSnapshot:
        """Safe counters only, available even after exhaustion for audit."""
        with self._lock:
            remaining = max(0.0, min(node._deadline for node in self._chain()) - self._now())
            return BudgetSnapshot(self._requests, self._redirects, self._raw_bytes,
                                  self._decoded_bytes, len(self._children), remaining)

    def checkpoint(self) -> BudgetCheckpoint:
        """Freeze the complete accounting tree under the shared root lock."""
        with self._lock:
            if self._parent is not None:
                raise ValueError('Checkpoint requires outbound budget root') from None
            now = self._now()
            def freeze(node: OutboundBudget) -> BudgetCheckpoint:
                # deadline - now can exceed the limit by float rounding at large monotonic
                # values; a checkpoint never reports more time than the node's own limit.
                return BudgetCheckpoint(node._limits, node._purpose,
                    min(float(node._limits.seconds), max(0.0, node._deadline - now)),
                    node._requests, node._redirects,
                    node._raw_bytes, node._decoded_bytes, node._blocked,
                    tuple(freeze(child) for child in node._children))
            return freeze(self)

    @classmethod
    def restore(
        cls, state: BudgetCheckpoint, *, elapsed_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> 'OutboundBudget':
        """Restore trusted counters minus known downtime, never reset budgets.

        Old live streams cannot be restored. Any new HTTP attempt charges a new
        request and all inherited bytes. This method does not provide fencing,
        DB durability, distributed atomicity, or a trustworthy wall-clock source.
        """
        try:
            if isinstance(elapsed_seconds, bool) or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Invalid outbound budget recovery elapsed time') from None
        restored_at: float | None = None
        def rebuild(saved: BudgetCheckpoint, parent: OutboundBudget | None) -> OutboundBudget:
            nonlocal restored_at
            if not isinstance(saved, BudgetCheckpoint):
                raise ValueError('Invalid outbound budget checkpoint') from None
            node = cls(saved.limits, purpose=saved.purpose, clock=clock)
            if restored_at is None:
                restored_at = node._started
            if (not math.isfinite(saved.remaining_seconds) or not 0 <= saved.remaining_seconds <= saved.limits.seconds
                    or any(type(value) is not int or not 0 <= value <= cap for value, cap in (
                        (saved.requests, saved.limits.requests), (saved.redirects, saved.limits.redirects),
                        (saved.raw_bytes, saved.limits.raw_bytes), (saved.decoded_bytes, saved.limits.decoded_bytes)))
                    or len(saved.children) > saved.limits.children
                    or saved.blocked is not None and not isinstance(saved.blocked, BudgetReason)):
                raise ValueError('Invalid outbound budget checkpoint') from None
            node._requests, node._redirects = saved.requests, saved.redirects
            node._raw_bytes, node._decoded_bytes = saved.raw_bytes, saved.decoded_bytes
            node._blocked = saved.blocked
            node._deadline = restored_at + max(0.0, saved.remaining_seconds - elapsed_seconds)
            if parent is not None:
                node._attach(parent)
            node._children = [rebuild(child, node) for child in saved.children]
            if any(sum(getattr(child, key) for child in node._children) > getattr(node, key)
                   for key in ('_requests', '_redirects', '_raw_bytes', '_decoded_bytes')):
                raise ValueError('Invalid outbound budget checkpoint') from None
            return node
        return rebuild(state, None)


class OutboundRequestScope:
    """A non-persisted phase deadline and response caps over the original tree.

    All accounting and terminal state belong to the original budget. A phase
    timeout poisons that budget so a new scope cannot reset the operation.
    The same clock and lock are used for parent and phase deadline checks.
    """

    def __init__(self, budget: OutboundBudget, limits: RequestLimits, *, purpose=None):
        if not isinstance(limits, RequestLimits):
            raise ValueError('Invalid outbound request limits') from None
        try:
            self._purpose = budget._purpose if purpose is None else OutboundPurpose(purpose)
        except (TypeError, ValueError):
            raise ValueError('Invalid outbound purpose') from None
        self._budget, self._limits = budget, limits
        with budget._lock:
            chain = budget._check()
            self._deadline = min(node._deadline for node in chain)
            if limits.seconds is not None:
                deadline = budget._now() + limits.seconds
                if not math.isfinite(deadline):
                    raise ValueError('Invalid outbound request limits') from None
                self._deadline = min(self._deadline, deadline)

    def remaining_seconds(self) -> float:
        budget = self._budget
        with budget._lock:
            budget._check()
            now = budget._now()
            if now >= self._deadline:
                budget._blocked = BudgetReason.DEADLINE
                raise OutboundBudgetError(BudgetReason.DEADLINE, self._purpose) from None
            return max(0.0, min(self._deadline,
                *(node._deadline for node in budget._chain())) - now)

    def begin_request(self, *, redirect: bool = False) -> 'OutboundResponseBudget':
        with self._budget._lock:
            self.remaining_seconds()
            return self._budget.begin_request(redirect=redirect,
                response_raw_bytes=self._limits.response_raw_bytes,
                response_decoded_bytes=self._limits.response_decoded_bytes,
                purpose=self._purpose)


class OutboundResponseBudget:
    """One stream's raw and decoded limits plus all ancestor totals."""

    def __init__(self, budget: OutboundBudget, *, limits: RequestLimits = RequestLimits(), purpose=None):
        self._budget = budget
        self._limits = limits
        self._purpose = budget._purpose if purpose is None else purpose
        self._raw = self._decoded = 0
        self._closed = False

    def consume(self, *, raw_bytes: int = 0, decoded_bytes: int = 0) -> None:
        """Atomically charge an observed, bounded chunk before storing it.

        On rejection no counter is partially charged; this stream is terminal.
        Rejected chunks must be discarded and the actual stream closed by its
        owner. Raw and decoded can be charged separately around decompression.
        """
        if any(type(value) is not int or value < 0 for value in (raw_bytes, decoded_bytes)):
            raise ValueError('Invalid outbound budget charge') from None
        budget = self._budget
        with budget._lock:
            if self._closed:
                raise OutboundBudgetError(BudgetReason.CLOSED, self._purpose) from None
            try:
                chain = budget._check()
                for current, delta, cap, reason in (
                    (self._raw, raw_bytes, self._limits.response_raw_bytes, BudgetReason.RESPONSE_RAW_BYTES),
                    (self._decoded, decoded_bytes, self._limits.response_decoded_bytes, BudgetReason.RESPONSE_DECODED_BYTES),
                ):
                    if cap is not None and current + delta > cap:
                        budget._blocked = reason
                        raise OutboundBudgetError(reason, self._purpose)
                for node in chain:
                    if self._raw + raw_bytes > node._limits.response_raw_bytes:
                        budget._blocked = BudgetReason.RESPONSE_RAW_BYTES
                        raise OutboundBudgetError(BudgetReason.RESPONSE_RAW_BYTES, self._purpose)
                    if self._decoded + decoded_bytes > node._limits.response_decoded_bytes:
                        budget._blocked = BudgetReason.RESPONSE_DECODED_BYTES
                        raise OutboundBudgetError(BudgetReason.RESPONSE_DECODED_BYTES, self._purpose)
                    for key, delta, reason in (('_raw_bytes', raw_bytes, BudgetReason.RAW_BYTES),
                                               ('_decoded_bytes', decoded_bytes, BudgetReason.DECODED_BYTES)):
                        if getattr(node, key) + delta > getattr(node._limits, key[1:]):
                            node._blocked = reason
                            raise OutboundBudgetError(reason, self._purpose)
            except OutboundBudgetError:
                self._closed = True
                raise
            for node in chain:
                node._raw_bytes += raw_bytes
                node._decoded_bytes += decoded_bytes
            self._raw += raw_bytes
            self._decoded += decoded_bytes

    def remaining_decoded_bytes(self) -> int:
        """Maximum next decoder output; do not decompress unbounded then check.

        A transport should also cap raw reads and handle allowance=0 itself;
        decompressor APIs often interpret max_length=0 as unlimited output.
        """
        return self._remaining_bytes(decoded=True)

    def remaining_raw_bytes(self) -> int:
        """Maximum next wire input, clipped by response and ancestor limits."""
        return self._remaining_bytes(decoded=False)

    def _remaining_bytes(self, *, decoded: bool) -> int:
        budget = self._budget
        with budget._lock:
            if self._closed:
                raise OutboundBudgetError(BudgetReason.CLOSED, self._purpose) from None
            chain = budget._check()
            if decoded:
                remaining = min(min(node._limits.response_decoded_bytes - self._decoded,
                                    node._limits.decoded_bytes - node._decoded_bytes) for node in chain)
                cap = self._limits.response_decoded_bytes
                return remaining if cap is None else min(remaining, cap - self._decoded)
            remaining = min(min(node._limits.response_raw_bytes - self._raw,
                                node._limits.raw_bytes - node._raw_bytes) for node in chain)
            cap = self._limits.response_raw_bytes
            return remaining if cap is None else min(remaining, cap - self._raw)

    def close(self) -> None:
        """Terminal local handle only; the adapter must close the real stream."""
        with self._budget._lock:
            self._closed = True


_GROUP_MAX_MEMBERS = 8
_GROUP_REASONS = (
    BudgetReason.DEADLINE, BudgetReason.REQUESTS, BudgetReason.REDIRECTS,
    BudgetReason.RESPONSE_RAW_BYTES, BudgetReason.RESPONSE_DECODED_BYTES,
    BudgetReason.RAW_BYTES, BudgetReason.DECODED_BYTES,
    BudgetReason.CHILDREN, BudgetReason.CLOSED,
)


class OutboundBudgetGroup:
    """Temporary atomic view over original roots, never a durable budget.

    One comparable path per root preserves the checkpoint child-sum invariant.
    Root strong references make the global id lock order stable for its lifetime.
    Callers must not enter this view while already holding a different root lock.
    No lock is held across network, decoder, persistence or consumer work.
    """

    def __init__(self, budgets: tuple[OutboundBudget, ...]):
        if (type(budgets) is not tuple or not 1 <= len(budgets) <= _GROUP_MAX_MEMBERS
                or any(type(node) is not OutboundBudget for node in budgets)):
            raise ValueError('Invalid outbound budget group') from None
        paths = {}
        for leaf in budgets:
            chain, seen = [], set()
            node = leaf
            while node is not None:
                if type(node) is not OutboundBudget or id(node) in seen:
                    raise ValueError('Invalid outbound budget group') from None
                seen.add(id(node))
                chain.append(node)
                node = node._parent
            root = chain[-1]
            if any(item._lock is not root._lock or item._clock is not root._clock for item in chain):
                raise ValueError('Invalid outbound budget group') from None
            old = paths.get(id(root))
            if old is not None:
                if any(item is leaf for item in old):
                    continue
                if not any(item is old[0] for item in chain):
                    raise ValueError('Invalid outbound budget group') from None
            paths[id(root)] = tuple(chain)
        chains = tuple(paths[key] for key in sorted(paths))
        roots = tuple(chain[-1] for chain in chains)
        if (len({id(root._lock) for root in roots}) != len(roots)
                or any(root._clock is not roots[0]._clock for root in roots)):
            raise ValueError('Invalid outbound budget group') from None
        self._roots, self._chains = roots, chains
        self._leaves = tuple(chain[0] for chain in chains)
        self._nodes = tuple(node for chain in chains for node in chain)
        self._clock = roots[0]._clock
        purposes = {leaf._purpose for leaf in self._leaves}
        self._purpose = next(iter(purposes)) if len(purposes) == 1 else OutboundPurpose.METADATA

    @contextmanager
    def _locked(self):
        acquired = []
        try:
            for root in self._roots:
                root._lock.acquire()
                acquired.append(root._lock)
            yield
        finally:
            for lock in reversed(acquired):
                lock.release()

    def _terminal(self, reason):
        for leaf in self._leaves:
            if leaf._blocked is None:
                leaf._blocked = reason

    def _sample(self, response=None):
        now = _clock_sample(self._clock)
        if now is None or any(now < root._last_now for root in self._roots):
            self._terminal(BudgetReason.CLOSED)
            if response is not None:
                response._closed = True
            raise ValueError('Invalid outbound budget clock') from None
        for root in self._roots:
            root._last_now = now
        return now

    def _check(self, now, purpose, *, deadline=None, request=False, redirect=False,
               response=None, raw=0, decoded=0):
        existing = [node._blocked for node in self._nodes if node._blocked is not None]
        failures, local = [], []
        for node in self._nodes:
            if now >= node._deadline:
                failures.append((node, BudgetReason.DEADLINE))
            if request:
                if node._requests >= node._limits.requests:
                    failures.append((node, BudgetReason.REQUESTS))
                if redirect and node._redirects >= node._limits.redirects:
                    failures.append((node, BudgetReason.REDIRECTS))
            if response is not None:
                if response._raw + raw > node._limits.response_raw_bytes:
                    local.append(BudgetReason.RESPONSE_RAW_BYTES)
                if response._decoded + decoded > node._limits.response_decoded_bytes:
                    local.append(BudgetReason.RESPONSE_DECODED_BYTES)
                if node._raw_bytes + raw > node._limits.raw_bytes:
                    failures.append((node, BudgetReason.RAW_BYTES))
                if node._decoded_bytes + decoded > node._limits.decoded_bytes:
                    failures.append((node, BudgetReason.DECODED_BYTES))
        if deadline is not None and now >= deadline:
            local.append(BudgetReason.DEADLINE)
        if response is not None:
            limits = response._scope._limits
            if limits.response_raw_bytes is not None and response._raw + raw > limits.response_raw_bytes:
                local.append(BudgetReason.RESPONSE_RAW_BYTES)
            if limits.response_decoded_bytes is not None and response._decoded + decoded > limits.response_decoded_bytes:
                local.append(BudgetReason.RESPONSE_DECODED_BYTES)
        candidates = existing or (local + [reason for _, reason in failures])
        if candidates:
            reason = min(candidates, key=_GROUP_REASONS.index)
            for node, failure in sorted(failures, key=lambda item: _GROUP_REASONS.index(item[1])):
                if node._blocked is None:
                    node._blocked = failure
            self._terminal(reason)
            if response is not None:
                response._closed = True
            raise OutboundBudgetError(reason, purpose) from None

    def remaining_seconds(self) -> float:
        with self._locked():
            now = self._sample()
            self._check(now, self._purpose)
            return min(node._deadline for node in self._nodes) - now

    def request_scope(self, limits: RequestLimits = RequestLimits(), *, purpose=None):
        return OutboundGroupRequestScope(self, limits, purpose=purpose)


class OutboundGroupRequestScope:
    """One phase across all redirects, borrowing original counter trees."""

    def __init__(self, group, limits, *, purpose=None):
        if type(limits) is not RequestLimits:
            raise ValueError('Invalid outbound request limits') from None
        checked = None
        try:
            checked = group._purpose if purpose is None else OutboundPurpose(purpose)
        except (TypeError, ValueError):
            pass
        if checked is None:
            raise ValueError('Invalid outbound purpose') from None
        self._group, self._limits, self._purpose = group, limits, checked
        with group._locked():
            now = group._sample()
            group._check(now, self._purpose)
            deadline = min(node._deadline for node in group._nodes)
            if limits.seconds is not None:
                phase = now + limits.seconds
                if not math.isfinite(phase):
                    raise ValueError('Invalid outbound request limits') from None
                deadline = min(deadline, phase)
            self._deadline = deadline

    def remaining_seconds(self) -> float:
        group = self._group
        with group._locked():
            now = group._sample()
            group._check(now, self._purpose, deadline=self._deadline)
            return min(self._deadline, *(node._deadline for node in group._nodes)) - now

    def begin_request(self, *, redirect: bool = False):
        if type(redirect) is not bool:
            raise ValueError('Invalid outbound budget charge') from None
        group = self._group
        with group._locked():
            now = group._sample()
            group._check(now, self._purpose, deadline=self._deadline, request=True, redirect=redirect)
            response = OutboundGroupResponseBudget(self)
            updates = [(node, node._requests + 1, node._redirects + int(redirect)) for node in group._nodes]
            for node, requests, redirects in updates:
                node._requests, node._redirects = requests, redirects
            return response


class OutboundGroupResponseBudget:
    """A local response cap; all cumulative accounting stays in original roots."""

    def __init__(self, scope):
        self._scope = scope
        self._raw = self._decoded = 0
        self._closed = False

    def _check(self):
        scope = self._scope
        if self._closed:
            raise OutboundBudgetError(BudgetReason.CLOSED, scope._purpose) from None
        now = scope._group._sample(self)
        return now

    def consume(self, *, raw_bytes: int = 0, decoded_bytes: int = 0) -> None:
        if any(type(value) is not int or value < 0 for value in (raw_bytes, decoded_bytes)):
            raise ValueError('Invalid outbound budget charge') from None
        scope, group = self._scope, self._scope._group
        with group._locked():
            now = self._check()
            group._check(now, scope._purpose, deadline=scope._deadline,
                         response=self, raw=raw_bytes, decoded=decoded_bytes)
            updates = [(node, node._raw_bytes + raw_bytes, node._decoded_bytes + decoded_bytes)
                       for node in group._nodes]
            new_raw, new_decoded = self._raw + raw_bytes, self._decoded + decoded_bytes
            for node, raw, decoded in updates:
                node._raw_bytes, node._decoded_bytes = raw, decoded
            self._raw, self._decoded = new_raw, new_decoded

    def _remaining(self, *, decoded):
        scope, group = self._scope, self._scope._group
        with group._locked():
            now = self._check()
            group._check(now, scope._purpose, deadline=scope._deadline, response=self)
            key, current = ('decoded', self._decoded) if decoded else ('raw', self._raw)
            remaining = min(min(getattr(node._limits, key + '_bytes') - getattr(node, '_' + key + '_bytes'),
                                getattr(node._limits, 'response_' + key + '_bytes') - current)
                            for node in group._nodes)
            cap = getattr(scope._limits, 'response_' + key + '_bytes')
            return remaining if cap is None else min(remaining, cap - current)

    def remaining_raw_bytes(self) -> int:
        return self._remaining(decoded=False)

    def remaining_decoded_bytes(self) -> int:
        return self._remaining(decoded=True)

    def close(self) -> None:
        with self._scope._group._locked():
            self._closed = True
