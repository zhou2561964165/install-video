"""Admin M1 Task 11: the admin app against contract 1.0.0-proposal.20261028.3 (offline).

Routes (method + path) must equal the contract's 23 operations; every 200 response model must carry
exactly the schema's property names (recursively through $ref) with all required ones; list query
parameters must equal the contract's. Values/enums are covered by the PG tests.
"""
import hashlib
import os
from pathlib import Path

import pytest
import yaml
from fastapi.routing import APIRoute
from sqlalchemy import create_engine

from app.admin.app import create_admin_app
from app.admin.config import AdminSettings
from app.services import admin_queries

CONTRACT = Path(os.environ.get('ADMIN_CONTRACT_PATH', r'C:\Users\zxk\.codex\worktrees\52fd\install_video\docs\production'
                               r'\admin-api-v1.openapi.yaml'))
SHA256 = '5af2352ab3e5100f2bbd3044fa3e6d01c2e3beddb098b24e989905e8bae5a7e8'
pytestmark = pytest.mark.skipif(not CONTRACT.exists(), reason='contract file not available')


@pytest.fixture(scope='module')
def document():
    return yaml.safe_load(CONTRACT.read_text(encoding='utf8'))


@pytest.fixture(scope='module')
def routes():
    settings = AdminSettings(cookie_path='/api/admin/v1', allowed_origins=('https://a.example',), csrf_secret=b'k' * 32)
    app = create_admin_app(settings, create_engine('sqlite://'))
    flat = []
    for route in app.routes:  # FastAPI >= 0.14x wraps included routers (no prefixes are used here)
        flat.extend(route.original_router.routes if hasattr(route, 'original_router') else [route])
    return {(method.lower(), route.path): route for route in flat if isinstance(route, APIRoute)
            for method in route.methods}


def operations(document):
    return {(method, path): operation for path, item in document['paths'].items()
            for method, operation in item.items() if method in ('get', 'post', 'patch', 'put', 'delete')}


def test_contract_hash_pinned():
    assert hashlib.sha256(CONTRACT.read_bytes()).hexdigest() == SHA256


def test_all_23_operations_routed(document, routes):
    expected = set(operations(document))
    assert len(expected) == 23 and set(routes) == expected


def _ref(schema):
    if not isinstance(schema, dict):
        return None
    if '$ref' in schema:
        return schema['$ref'].split('/')[-1]
    for key in ('anyOf', 'oneOf', 'allOf'):
        for option in schema.get(key, []):
            found = _ref(option)
            if found:
                return found
    if schema.get('type') == 'array' or 'items' in schema:
        return _ref(schema.get('items'))
    return None


def _compare(name, contract_schema, model_schema, components, defs, seen, problems):
    if name in seen:
        return
    seen.add(name)
    contract_props = contract_schema.get('properties', {})
    model_props = model_schema.get('properties', {})
    if set(contract_props) != set(model_props):
        problems.append((name, 'properties', sorted(set(contract_props) ^ set(model_props))))
    missing = set(contract_schema.get('required', [])) - set(model_schema.get('required', []))
    if missing:
        problems.append((name, 'required', sorted(missing)))
    for prop, contract_prop in contract_props.items():
        child = _ref(contract_prop)
        model_child = _ref(model_props.get(prop, {}))
        if child and child in components:
            if not model_child or model_child not in defs:
                if components[child].get('properties'):
                    problems.append((name, prop, 'nested model missing'))
                continue
            _compare(child, components[child], defs[model_child], components, defs, seen, problems)


def test_response_models_match_schemas(document, routes):
    components = document['components']['schemas']
    problems = []
    for key, operation in operations(document).items():
        response = operation['responses'].get('200') or operation['responses'].get('204')
        content = (response or {}).get('content', {}).get('application/json')
        if not content or key == ('patch', '/users/{user_id}/access'):  # M1: closed (503), no success body yet
            continue
        name = _ref(content['schema'])
        model = routes[key].response_model
        assert model is not None, key
        schema = model.model_json_schema(ref_template='#/$defs/{model}')
        defs = dict(schema.get('$defs', {}))
        defs[model.__name__] = schema
        _compare(name, components[name], schema, components, defs, set(), problems)
    assert problems == []


def test_list_query_params_match(document):
    parameters = document['components']['parameters']
    for (method, path), operation in operations(document).items():
        if not operation['operationId'].startswith('adminList'):
            continue
        query = [parameters[p['$ref'].split('/')[-1]] if '$ref' in p else p for p in operation.get('parameters', [])]
        names = {p['name'] for p in query if p.get('in') == 'query'}
        spec = admin_queries.RESOURCES[operation['operationId']]
        assert names == {'page', 'page_size', 'sort'} | {f.name for f in spec.filters}, operation['operationId']
        sort = next(p for p in query if p.get('name') == 'sort')['schema']
        assert list(spec.sorts) == sort['enum'] and spec.default_sort == sort['default']
