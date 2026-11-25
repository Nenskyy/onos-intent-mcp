#!/usr/bin/env python3
"""Operator-only intent baseline preparation and independent ping verification."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('apply', 'verify'))
    parser.add_argument('state', choices=('G', 'B'))
    parser.add_argument('--onos-url', default=os.environ.get('ONOS_URL', 'http://10.0.2.2:8181'))
    parser.add_argument('--control-url', default=os.environ.get('ONOS_CONTROL_URL', 'http://127.0.0.1:9090'))
    parser.add_argument('--app-id', default='org.onosproject.cli')
    parser.add_argument('--count', type=int, choices=(1, 3), default=3)
    args = parser.parse_args()
    spec = json.loads((HERE / f'state-{args.state}.json').read_text())
    topology = json.loads((HERE / 'network.json').read_text())
    by_name = {h['name']: h for h in topology['hosts']}
    id_to_name = {h['mac'].lower() + '/None': h['name'] for h in topology['hosts']}
    macs = {h['mac'].lower() for h in topology['hosts']}
    selected = {frozenset((p['source'], p['destination'])) for p in spec['pair_expectations'] if p['expected_reachable']}
    password = os.environ.get('ONOS_PASSWORD') or getpass.getpass('ONOS password: ')
    user = os.environ.get('ONOS_USER', 'onos')
    auth = 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    evidence = HERE / 'evidence' / f'{args.state}-{args.operation}-{stamp}'
    evidence.mkdir(parents=True)
    journal = []

    def request(base, path, method='GET', payload=None):
        headers = {'Accept': 'application/json'}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        if base == args.onos_url:
            headers['Authorization'] = auth
        body = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(base.rstrip('/') + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=40) as response:
            raw = response.read().decode()
            result = json.loads(raw) if raw else {}
            journal.append({'time': datetime.now(timezone.utc).isoformat(), 'method': method, 'path': path, 'payload': payload, 'status': response.status, 'result': result})
            return result

    def inventory():
        return request(args.onos_url, '/onos/v1/intents')['intents']

    def pair(intent):
        endpoints = [intent.get('one'), intent.get('two')]
        if not all(endpoints):
            endpoints = intent.get('resources', [])
        if len(endpoints) != 2 or any(x not in id_to_name for x in endpoints):
            return None
        return frozenset(id_to_name[x] for x in endpoints)

    def current(intent):
        return intent.get('state') not in ('WITHDRAWN', 'WITHDRAWING', 'PURGED')

    def delete_intent(intent):
        key = intent.get('key') or intent['id']
        if str(key).startswith('0x'):
            key = str(int(key, 16))
        path = '/onos/v1/intents/' + urllib.parse.quote(intent['appId'], safe='') + '/' + urllib.parse.quote(str(key), safe='')
        request(args.onos_url, path, 'DELETE')

    try:
        status = request(args.control_url, '/status')
        control_hosts = status.get('hosts', {})
        if set(control_hosts) != set(by_name):
            raise RuntimeError('Control service host names do not match the eight-host topology.')
        for name, host in by_name.items():
            actual = control_hosts[name]
            if actual.get('ip') != host['ip'].split('/')[0] or actual.get('mac', '').lower() != host['mac'].lower() or actual.get('switch') != host['switch']:
                raise RuntimeError(f'Host identity/attachment mismatch: {name}')
        if any(link.get('status') != 'up' for link in status.get('links', [])):
            raise RuntimeError('A physical link is down or unknown; restore it before preparing this intent baseline.')
        hosts = request(args.onos_url, '/onos/v1/hosts')['hosts']
        if not set(id_to_name).issubset({h['id'] for h in hosts}):
            raise RuntimeError('ONOS has not discovered all eight hosts; generate ARP discovery first.')
        before = inventory()
        (evidence / 'before-intents.json').write_text(json.dumps(before, indent=2))

        if args.operation == 'apply':
            live = [i for i in before if current(i)]
            if any(pair(i) is None or i.get('appId') != args.app_id or i.get('type') != 'HostToHostIntent' for i in live):
                raise RuntimeError('Unexpected active intent or owner; refusing automatic cleanup in a potentially shared controller.')
            # Remove only the MCP-managed exact host-pair drops in this hospital.
            flows = request(args.onos_url, '/onos/v1/flows').get('flows', [])
            for flow in flows:
                criteria = {c.get('type'): c for c in flow.get('selector', {}).get('criteria', [])}
                if str(flow.get('priority')) != '50123' or flow.get('appId') != args.app_id:
                    continue
                if criteria.get('ETH_SRC', {}).get('mac', '').lower() not in macs or criteria.get('ETH_DST', {}).get('mac', '').lower() not in macs:
                    continue
                if set(criteria) != {'ETH_SRC', 'ETH_DST'}:
                    raise RuntimeError('Unexpected managed blocking rule; inspect rather than broadening cleanup.')
                path = '/onos/v1/flows/' + urllib.parse.quote(flow['deviceId'], safe='') + '/' + urllib.parse.quote(str(flow['id']), safe='')
                request(args.onos_url, path, 'DELETE')
            keep = set()
            for intent in live:
                endpoints = pair(intent)
                if endpoints in selected and intent.get('state') == 'INSTALLED' and endpoints not in keep:
                    keep.add(endpoints)
                else:
                    delete_intent(intent)
            deadline = time.monotonic() + 30
            while True:
                pending = [i for i in inventory() if current(i) and pair(i) not in keep]
                if not pending:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('Intent withdrawal did not converge; no replacements were created.')
                time.sleep(1)
            for expectation in spec['pair_expectations']:
                endpoints = frozenset((expectation['source'], expectation['destination']))
                if not expectation['expected_reachable'] or endpoints in keep:
                    continue
                src, dst = expectation['source'], expectation['destination']
                request(args.onos_url, '/onos/v1/intents', 'POST', {'type': 'HostToHostIntent', 'appId': args.app_id, 'priority': 100, 'one': by_name[src]['mac'] + '/None', 'two': by_name[dst]['mac'] + '/None'})
            deadline = time.monotonic() + 30
            while True:
                active = [i for i in inventory() if current(i)]
                if len(active) == len(selected) and {pair(i) for i in active} == selected and all(i.get('state') == 'INSTALLED' for i in active):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('Expected six intents did not reach INSTALLED; inspect controller state.')
                time.sleep(1)
            print(f'{args.state}: six expected intents installed. Run verify next; this is not a reachability pass.')
        else:
            rows = []
            for expectation in spec['pair_expectations']:
                for src, dst in [(expectation['source'], expectation['destination']), (expectation['destination'], expectation['source'])]:
                    result = request(args.control_url, '/command', 'POST', {'command': 'ping', 'source': src, 'destination': dst, 'count': args.count})
                    match = re.search(r'(\d+) packets transmitted,\s*(\d+) (?:packets )?received', result.get('output', ''))
                    sent, received = map(int, match.groups()) if match else (None, None)
                    expected_received = args.count if expectation['expected_reachable'] else 0
                    passed = not result.get('error') and sent == args.count and received == expected_received
                    row = {'source': src, 'destination': dst, 'expected_reachable': expectation['expected_reachable'], 'sent': sent, 'received': received, 'passed': bool(passed), 'response': result}
                    rows.append(row)
                    print(f'{len(rows):02}/56 {src:8} -> {dst:8}: ' + ('OK' if passed else 'MISMATCH'), flush=True)
                    (evidence / 'connectivity.json').write_text(json.dumps(rows, indent=2))
            passed = all(r['passed'] for r in rows)
            summary = {'state': args.state, 'count_per_direction': args.count, 'directed_checks': len(rows), 'passed': passed, 'mismatches': [r for r in rows if not r['passed']], 'classification': 'three-probe baseline gate' if args.count == 3 else 'one-probe smoke check'}
            (evidence / 'summary.json').write_text(json.dumps(summary, indent=2))
            print(f'{args.state}: ' + ('PASS' if passed else 'INVALID START STATE') + f' ({sum(r["passed"] for r in rows)}/56 checks match).')
            if not passed:
                raise RuntimeError('Reachability differs from specification. Do not start model trials.')
        (evidence / 'after-intents.json').write_text(json.dumps(inventory(), indent=2))
    except Exception as error:
        (evidence / 'error.txt').write_text(f'{type(error).__name__}: {error}\n')
        raise
    finally:
        (evidence / 'requests.json').write_text(json.dumps(journal, indent=2))
        print(f'Evidence: {evidence}')


if __name__ == '__main__':
    main()
