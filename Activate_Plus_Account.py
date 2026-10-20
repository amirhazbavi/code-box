#!/usr/bin/env python3
"""Manually grant/revoke a CodeBox Plus entitlement after authorization.
Requires CODEBOX_ADMIN_KEY on the server and requests on this machine.
"""
import getpass, os, requests

base = input('CodeBox server URL [http://127.0.0.1:8765]: ').strip() or 'http://127.0.0.1:8765'
email = input('Account email: ').strip().lower()
plan = input('Plan to set [plus/free] (default plus): ').strip().lower() or 'plus'
if plan not in {'plus', 'free'}:
    raise SystemExit('Plan must be plus or free.')
key = os.environ.get('CODEBOX_ADMIN_KEY') or getpass.getpass('Server admin key: ')
try:
    response = requests.post(base.rstrip('/') + '/api/admin/grant-plus',
                             headers={'X-Admin-Key': key},
                             json={'email': email, 'plan': plan}, timeout=15)
    try: data = response.json()
    except Exception: data = {'error': response.text[:500]}
    if not response.ok:
        raise SystemExit(f'Activation failed ({response.status_code}): {data.get("error", "Unknown error")}')
    print(f"Updated {data['email']} to plan={data['plan']}. Ask the user to sign out and sign in again.")
except requests.RequestException as exc:
    raise SystemExit(f'Could not reach server: {exc}')
