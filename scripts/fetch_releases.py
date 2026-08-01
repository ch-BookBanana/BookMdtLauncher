# -*- coding: utf-8 -*-
import sys, os, json, requests

TOKEN = None
if len(sys.argv) > 1:
    TOKEN = sys.argv[1]
else:
    TOKEN = os.environ.get('GITHUB_TOKEN')

if not TOKEN:
    print('No token provided (argv[1] or GITHUB_TOKEN).')
    sys.exit(2)

repo = 'Anuken/Mindustry'
url = f'https://api.github.com/repos/{repo}/releases'
params = {'page': 1, 'per_page': 5}
headers = {'Authorization': f'token {TOKEN}', 'Accept': 'application/vnd.github.v3+json'}

try:
    r = requests.get(url, headers=headers, params=params, timeout=15)
    if r.status_code == 200:
        data = r.json()
        out_path = os.path.join('BML', 'test.json')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print('Saved releases to', out_path)
        sys.exit(0)
    else:
        print('HTTP', r.status_code)
        try:
            print(r.json())
        except Exception:
            print(r.text)
        sys.exit(3)
except Exception as e:
    print('Error:', e)
    sys.exit(4)
