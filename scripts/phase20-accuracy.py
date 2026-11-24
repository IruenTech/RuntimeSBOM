#!/usr/bin/env python3
"""Ground-truth-vs-CycloneDX accuracy for explicitly scoped fixture artifacts.

The truth file MUST originate outside the SBOM collector (e.g. known build inputs).
Per-instance identity = Maven PURL + SHA-256 + exact source suffix. Duplicate
class-loader instances are counted separately; execution attribution is checked
separately from component identification. NOT an estimate of real WAS recall.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import json
from typing import Any
from urllib.parse import unquote


def props(component: dict) -> dict:
    return {p.get('name'): p.get('value') for p in component.get('properties', []) if isinstance(p, dict)}


def sha256(component: dict) -> str:
    for item in component.get('hashes', []):
        if item.get('alg') == 'SHA-256':
            return str(item.get('content', '')).lower()
    return ''


def norm_source(value: str) -> str:
    return unquote(str(value).replace('\\', '/')).rstrip('/')


def extract_evidence(component: dict) -> dict:
    p = props(component)
    try:
        count = int(p.get('runtimeSbom:observedMethodEntryCount', '-1'))
    except (TypeError, ValueError):
        count = -1
    return {'purl': component.get('purl', ''), 'sha256': sha256(component),
            'source': norm_source(p.get('runtimeSbom:source', '')),
            'loader': p.get('runtimeSbom:classLoader', ''),
            'count': count, 'state': p.get('runtimeSbom:runtimeEvidenceState', '')}


def ratio(a: int, b: int) -> float:
    return round(a / b, 6) if b else 0.0


def evaluate(truth: dict, sbom: dict) -> dict:
    if sbom.get('bomFormat') != 'CycloneDX' or sbom.get('specVersion') != '1.6':
        raise ValueError('Expected CycloneDX 1.6 JSON')
    expected = truth.get('expected')
    if not isinstance(expected, list) or not expected:
        raise ValueError('Independent ground truth must list at least one component')
    suffixes = [norm_source(e['sourceSuffix']) for e in expected]
    if any(not x for x in suffixes):
        raise ValueError('sourceSuffix must be nonempty')
    terms = truth.get('scopeTerms', [])
    if not terms or any(not isinstance(x, str) or not x for x in terms):
        raise ValueError('scopeTerms must be nonempty strings')
    for e in expected:
        if not all(e.get(k) for k in ('purl', 'sha256', 'sourceSuffix', 'evidenceState')):
            raise ValueError('Ground truth missing required identity field')
        if type(e.get('methodEntries')) is not int or e['methodEntries'] < 0:
            raise ValueError('methodEntries must be a nonnegative integer')
    found = [extract_evidence(c) for c in sbom.get('components', [])
             if isinstance(c, dict)]
    scoped = [c for c in found if any(term in c['source'] or term in c['purl'] for term in terms)]

    def source_key(src: str) -> str:
        matching = [s for s in set(suffixes) if src.endswith(s)]
        return max(matching, key=len) if matching else src

    def key(c: dict) -> tuple:
        return (c['purl'], c['sha256'].lower(), source_key(c['source']))

    wanted = Counter((e['purl'], e['sha256'].lower(), norm_source(e['sourceSuffix'])) for e in expected)
    actual = Counter(map(key, scoped))
    matched = sum(min(wanted[k], actual[k]) for k in wanted)
    tp, fp, fn = matched, len(scoped) - matched, len(expected) - matched
    p = ratio(tp, tp + fp)
    r = ratio(tp, tp + fn)
    f1 = round((2*p*r)/(p+r), 6) if p+r else 0.0

    expected_by_group = defaultdict(list)
    actual_by_group = defaultdict(list)
    for item in expected:
        expected_by_group[(item['purl'],item['sha256'].lower(),norm_source(item['sourceSuffix']))].append(item)
    for item in scoped:
        actual_by_group[key(item)].append(item)
    groups = []
    identity_execution_correct = True
    loader_unique = True
    for group, items in expected_by_group.items():
        observed = actual_by_group.get(group, [])
        exp_evidence = Counter((e['methodEntries'], e['evidenceState']) for e in items)
        got_evidence = Counter((e['count'], e['state']) for e in observed)
        counts_match = exp_evidence == got_evidence
        # Every component instance must have a distinct, nonblank loader token
        # within the same JAR identity. Loader tokens are runtime-specific.
        loaders = [x['loader'] for x in observed]
        unique_loaders = bool(loaders) and len(loaders) == len(set(loaders)) and all(loaders)
        identity_execution_correct &= counts_match
        loader_unique &= unique_loaders
        groups.append({'purl': group[0], 'sha256': group[1], 'sourceSuffix': group[2],
                       'expectedInstances': len(items), 'observedInstances': len(observed),
                       'expectedExecution': sorted([{'entries':n,'state':s} for n,s in exp_evidence.elements()], key=lambda x:x['entries']),
                       'observedExecution': sorted([{'entries':n,'state':s} for n,s in got_evidence.elements()], key=lambda x:x['entries']),
                       'exactExecution': counts_match, 'distinctLoaderTokens': unique_loaders})
    meta = props(sbom.get('metadata', {}))
    try:
        unattributed = int(meta.get('runtimeSbom:unattributedMethodEntries','0'))
    except (ValueError,TypeError):
        unattributed = -1
    clean_attribution = (unattributed == 0)
    passed = (tp == len(expected) and fp == 0 and fn == 0 and
              identity_execution_correct and loader_unique and clean_attribution)
    return {'schemaVersion': 1,'scope':'INDEPENDENT_SYNTHETIC_FIXTURE_GROUND_TRUTH_ONLY',
            'fixtureName':truth.get('name','unnamed'),'groundTruthSource': truth.get('groundTruthSource'),
            'expectedInstances':len(expected),'observedScopedInstances':len(scoped),
            'truePositives':tp,'falsePositives':fp,'falseNegatives':fn,
            'identityPrecision':p,'identityRecall':r,'identityF1':f1,
            'executionEvidenceExact':bool(identity_execution_correct),
            'classLoaderTokensDistinct':bool(loader_unique),
            'unattributedMethodEntries':unattributed,
            'strictFixturePass':bool(passed), 'groups':groups,
            'limitations':['Fixture-level accuracy does not estimate production OSS inventory recall or precision.',
                           'Only instrumented method entries are observable. Isolated class loaders may execute unobserved.',
                           'Ground truth must be independently constructed from known build inputs and expected calls.']}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--truth',required=True,type=Path)
    parser.add_argument('--sbom',required=True,type=Path)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--require-perfect',action='store_true')
    args=parser.parse_args()
    report=evaluate(json.loads(args.truth.read_text(encoding='utf-8')),
                    json.loads(args.sbom.read_text(encoding='utf-8')))
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('fixtureName','expectedInstances','observedScopedInstances',
        'truePositives','falsePositives','falseNegatives','identityPrecision','identityRecall',
        'identityF1','executionEvidenceExact','classLoaderTokensDistinct','strictFixturePass')},indent=2))
    return 0 if not args.require_perfect or report['strictFixturePass'] else 4


if __name__=='__main__':
    raise SystemExit(main())
