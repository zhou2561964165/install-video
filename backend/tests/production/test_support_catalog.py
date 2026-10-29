"""Support tickets Task 2: fixed issue types and reply templates (offline)."""
import pytest

from app.services import support_catalog as catalog


def test_categories_fixed():
    assert catalog.CATEGORIES == {
        'membership_not_credited': '会员付款后未到账',
        'download_failing': '下载一直失败',
        'login_problem': '账号无法登录',
        'other': '其他问题',
    }


def test_reissued_template_text():
    assert catalog.render('reissued', days=30) == '已为您补发 30 天会员，请刷新会员页查看'


def test_manual_templates_exact_and_reissued_not_manual():
    assert catalog.MANUAL_TEMPLATES == {'not_paid', 'already_active', 'download_help', 'login_help', 'generic'}
    assert 'reissued' not in catalog.MANUAL_TEMPLATES
    assert catalog.render('not_paid') == '经核实该订单未完成支付，未产生扣款'
    assert catalog.render('already_active') == '经核实您的会员已生效，请刷新会员页查看'
    assert catalog.render('generic') == '已收到您的反馈，我们会尽快处理'


def test_unknown_template_rejected():
    with pytest.raises(ValueError):
        catalog.render('anything_else')


def test_note_limit():
    assert catalog.NOTE_MAX == 500
