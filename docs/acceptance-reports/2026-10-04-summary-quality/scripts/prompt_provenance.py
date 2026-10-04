"""Extract literal summary system prompts without executing historical source.

Engineering: skills outrank plans; UI skills/tokens; configurable abilities;
narrow service boundaries and yt-dlp only through ytdlp_service.py.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[2]
SOURCE_PATH = 'backend/app/services/llm_service.py'
BASELINE_REF = 'b62f7d429becfc00a2db9140be505c9ffeb53a20'


def summary_system_prompt(source: str) -> str:
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_summary_request')
    for node in ast.walk(function):
        if not isinstance(node, ast.Dict):
            continue
        fields = {key.value: value for key, value in zip(node.keys, node.values) if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        role = fields.get('role')
        content = fields.get('content')
        if isinstance(role, ast.Constant) and role.value == 'system' and isinstance(content, ast.Constant) and isinstance(content.value, str):
            return content.value
    raise ValueError('No literal summary system prompt found')


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def main():
    output = ROOT / 'results' / 'provenance.json'
    if output.exists():
        raise SystemExit('Refusing to overwrite prompt provenance')
    before_source = subprocess.check_output(['git', 'show', f'{BASELINE_REF}:{SOURCE_PATH}'], cwd=PROJECT).decode('utf-8').replace('\r\n', '\n')
    after_source = (PROJECT / SOURCE_PATH).read_text(encoding='utf-8')
    rows = {}
    for phase, source in [('before', before_source), ('after', after_source)]:
        prompt = summary_system_prompt(source)
        rows[phase] = {
            'source_path': SOURCE_PATH,
            'source_ref': BASELINE_REF if phase == 'before' else '2026-10-04 evaluated worktree diff from baseline (only _summary_request system prompt changed)',
            'source_sha256_utf8_lf': sha256(source),
            'system_prompt_sha256_utf8': sha256(prompt),
            'system_prompt': prompt,
            'result_sha256': hashlib.sha256((ROOT / 'results' / f'{phase}.json').read_bytes()).hexdigest(),
        }
    output.write_text(json.dumps({
        'method': 'Post-evaluation provenance: literal prompts safely extracted via AST from the known pre-change Git source and evaluated after worktree. No historical source execution, model request or alteration of result/ledger evidence.',
        'engineering_rules': 'UI skills/tokens; skills outrank plans; configurable abilities; narrow interfaces and yt-dlp isolation.',
        'hash_encoding': 'Prompts UTF-8 exactly; source UTF-8 with CRLF normalized to LF; result files original bytes.',
        'phases': rows,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({phase: row['system_prompt_sha256_utf8'] for phase, row in rows.items()}))


if __name__ == '__main__':
    main()
