"""Offline contracts: synthetic hosts/IP data only; no resolver or network."""

import pytest

from app.services.outbound_policy import (
    OutboundPolicy, OutboundPolicyError, OutboundPurpose,
    OutboundUnavailableError, validate_url, select_public_addresses,
    validate_redirect,
)


def test_canonicalization_preserves_signed_query_and_hides_url_from_repr():
    target = validate_url('HTTPS://VIDEO.test.:443/a%2Fb?q=%2F%252F#private', 'source')
    assert target.url == 'https://video.test/a%2Fb?q=%2F%252F'
    assert (target.host, target.port, target.origin) == ('video.test', 443, ('https', 'video.test', 443))
    assert 'private' not in repr(target)
    assert 'q=' not in repr(target)
    assert validate_url('https://例子.test/a', 'metadata').host == 'xn--fsqu00a.test'


@pytest.mark.parametrize('url', [
    'file:///secret', 'gopher://video.test/', 'ftp://video.test/',
    'https:///v', 'https://@video.test/', 'https://u:p@video.test/',
    'https://video.test%40private.test/', 'https://%76ideo.test/',
    'https://video.test:/', 'https://video.test:0/', 'https://video.test:65536/',
    'https://video.test:+443/', 'https://video.test:0443/',
    'https://video.test:abc/', 'https://video.test\\private/',
    'https://video.test/a\nsecret', 'https://video.test/\x00',
    'https://video.test/\x7f', ' https://video.test/', 'https://video.test/a b',
    'https://video..test/', 'https://video.test../', 'https://-bad.test/',
    'https://bad_.test/', 'https://[fe80::1%25eth0]/',
    'http://2130706433/', 'http://0177.0.0.1/', 'http://0x7f000001/',
    'http://127.1/', 'http://0x7f.0.0.1/', 'http://0x7f.1/', 'http://127.00.0.1/',
    'http://999.1.1.1/', 'http://0xffffffff/', 'http://123.456/',
    'http://[8.8.8.8]/', 'http://2001:4860:4860::8888/',
])
def test_ambiguous_or_malformed_initial_url_is_invalid_without_echo(url):
    with pytest.raises(OutboundPolicyError) as caught:
        validate_url(url, 'source')
    error = caught.value
    assert error.code == 'invalid_url'
    assert error.status_code == 400
    assert url not in str(error)
    assert url not in repr(error)
    assert error.retryable is False
    assert error.public_detail() == {'error_type': 'invalid_url', 'error': '链接格式无效'}


def test_derived_malformed_url_is_blocked_and_exception_context_is_suppressed():
    with pytest.raises(OutboundPolicyError) as caught:
        validate_url('https://u:password@video.test/', 'media', initial=False)
    assert caught.value.code == 'outbound_blocked'
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_parser_and_resolver_exceptions_are_not_retained_as_sensitive_context():
    with pytest.raises(OutboundPolicyError) as malformed:
        validate_url('https://[not-an-ip-secret]/signed?q=private', 'source')
    assert malformed.value.__context__ is None
    def failing_answers():
        yield '8.8.8.8'
        raise RuntimeError('https://video.test/signed?token=private')
    with pytest.raises(OutboundPolicyError) as dns:
        select_public_addresses(validate_url('https://video.test/', 'source'), failing_answers())
    assert dns.value.reason == 'dns_failure'
    assert dns.value.__context__ is None


@pytest.mark.parametrize('ip', [
    '127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.1.1', '0.0.0.0',
    '224.0.0.1', '255.255.255.255', '169.254.169.254', '169.254.170.2',
    '100.100.100.200', '168.63.129.16', '192.0.2.1', '198.18.0.1',
    '198.51.100.1', '203.0.113.1', '192.0.0.9', '192.0.0.10',
    '[::]', '[::1]', '[fe80::1]', '[fc00::1]', '[ff02::1]', '[2001:db8::1]',
    '[::ffff:127.0.0.1]', '[::ffff:10.0.0.1]', '[::ffff:169.254.169.254]',
    '[64:ff9b::a9fe:a9fe]', '[64:ff9b:1::808:808]',
    '[2002:0808:0808::1]', '[2001:0:1234::1]', '[::8.8.8.8]', '[2001:20::1]',
])
def test_literal_special_address_is_blocked(ip):
    with pytest.raises(OutboundPolicyError, match='来源地址不符合安全策略') as caught:
        validate_url(f'https://{ip}/x', 'media')
    assert caught.value.code == 'outbound_blocked'


def test_mapped_public_ip_uses_ipv4_policy_and_normalizes_for_connection():
    target = validate_url('https://[::ffff:8.8.8.8]/x', 'media')
    assert target.host == '::ffff:808:808'
    assert select_public_addresses(target, ['::ffff:8.8.8.8']) == ('8.8.8.8',)
    policy = OutboundPolicy(denied_cidrs=('8.8.8.0/24',))
    with pytest.raises(OutboundPolicyError):
        validate_url('https://[::ffff:8.8.8.8]/x', 'media', policy)
    policy6 = OutboundPolicy(denied_cidrs=('::ffff:808:808/128',))
    with pytest.raises(OutboundPolicyError):
        validate_url('https://[::ffff:8.8.8.8]/x', 'media', policy6)


def test_generic_platform_support_and_explicit_narrow_domain_boundary():
    for host in ('youtube.com', 'api.bilibili.com', 'archive.org', 'video42.other.test', 'face.de', 'abc.be'):
        assert validate_url(f'https://{host}/x', OutboundPurpose.METADATA).host == host
    narrow = OutboundPolicy(allowed_host_roots=('bilivideo.com',))
    assert validate_url('https://cdn.bilivideo.com/x', 'media', narrow).host == 'cdn.bilivideo.com'
    for host in ('evilbilivideo.com', 'bilivideo.com.evil.test'):
        with pytest.raises(OutboundPolicyError):
            validate_url(f'https://{host}/', 'media', narrow)


def test_utf8_byte_limit_default_ports_and_operator_extension():
    with pytest.raises(OutboundPolicyError):
        validate_url('https://video.test/' + '字' * 2731, 'source')
    with pytest.raises(OutboundPolicyError) as caught:
        validate_url('https://video.test:8443/', 'source')
    assert caught.value.code == 'outbound_blocked'
    target = validate_url('https://video.test:8443/', 'source', OutboundPolicy(allowed_ports=frozenset({80, 443, 8443})))
    assert target.port == 8443


def test_mixed_dns_returns_only_safe_deduplicated_candidates_and_new_result_rechecks():
    policy = OutboundPolicy(denied_cidrs=('9.9.9.9/32',))
    target = validate_url('https://video.test/', 'metadata', policy)
    assert select_public_addresses(target, ['10.0.0.1', '8.8.8.8', '::1', '8.8.8.8', '9.9.9.9', '2001:4860:4860::8888'], policy) == ('8.8.8.8', '2001:4860:4860::8888')
    with pytest.raises(OutboundPolicyError):
        select_public_addresses(target, ['127.0.0.1'], policy)


@pytest.mark.parametrize('answers', [[], ['bogus'], ['010.0.0.1'], ['fe80::1%eth0'], ['127.0.0.1']])
def test_no_safe_dns_candidates_fail_closed(answers):
    with pytest.raises(OutboundPolicyError):
        select_public_addresses(validate_url('https://video.test/', 'source'), answers)


def test_dns_limit_stops_bounded_iteration_even_when_early_answer_is_safe():
    target = validate_url('https://video.test/', 'source')
    observed = []
    def answers():
        for index in range(1000):
            observed.append(index)
            yield '8.8.8.8'
    with pytest.raises(OutboundPolicyError):
        select_public_addresses(target, answers(), OutboundPolicy(max_dns_answers=2))
    assert observed == [0, 1, 2]


def test_literal_target_cannot_accept_substituted_dns_answer():
    with pytest.raises(OutboundPolicyError):
        select_public_addresses(validate_url('https://8.8.8.8/', 'source'), ['1.1.1.1'])


def test_each_redirect_revalidates_relative_location_and_origin_downgrade_exception():
    current = validate_url('https://video.test/a/start?q=secret', 'source')
    assert validate_redirect(current, '../next?q=%2F').url == 'https://video.test/next?q=%2F'
    for location in ('http://video.test/x', 'http://other.test/', '//127.0.0.1/', 'https://u:p@video.test/'):
        with pytest.raises(OutboundPolicyError):
            validate_redirect(current, location)
    policy = OutboundPolicy(downgrade_origins=frozenset({('https', 'video.test', 443)}))
    assert validate_redirect(current, 'http://video.test/x', policy).scheme == 'http'
    with pytest.raises(OutboundPolicyError):
        validate_redirect(validate_url('https://other.test/', 'source'), 'http://other.test/', policy)
    with pytest.raises(OutboundPolicyError):
        validate_redirect(current, '/next', OutboundPolicy(follow_redirects=False))


def test_provider_requires_separate_exact_https_authority_allowlist():
    with pytest.raises(OutboundPolicyError):
        validate_url('https://provider.test/v1', 'provider')
    policy = OutboundPolicy(provider_origins=frozenset({('https', 'provider.test', 443)}))
    assert validate_url('https://provider.test/v1', 'provider', policy).purpose is OutboundPurpose.PROVIDER
    for url in ('http://provider.test/v1', 'https://sub.provider.test/v1', 'https://evil.test/v1'):
        with pytest.raises(OutboundPolicyError):
            validate_url(url, 'provider', policy)
    error = OutboundUnavailableError()
    assert (error.code, error.status_code, str(error)) == ('outbound_unavailable', 503, '安全访问通道暂不可用')


def test_asr_purpose_uses_public_source_scope_without_provider_privilege():
    target = validate_url('https://video42.other.test/audio', 'asr')
    assert target.purpose is OutboundPurpose.ASR
    with pytest.raises(OutboundPolicyError):
        validate_url('https://127.0.0.1/audio', 'asr')
    with pytest.raises(OutboundPolicyError):
        validate_url(target.url, 'provider')


@pytest.mark.parametrize('kwargs', [{'allowed_ports': frozenset({0})}, {'max_url_bytes': 0}, {'max_dns_answers': 0}, {'denied_cidrs': ('secret-invalid-network',)}])
def test_invalid_operator_policy_fails_with_fixed_configuration_error(kwargs):
    with pytest.raises(ValueError) as caught:
        OutboundPolicy(**kwargs)
    assert str(caught.value) == 'Invalid outbound policy configuration'
