import json
d=json.load(open('/out/semgrep.json'))
for r in sorted(d['results'],key=lambda r:(r['path'],r['start']['line'])):
    m=r['extra'].get('metadata',{})
    print(r['path'],r['start']['line'],r['check_id'].split('.')[-1],'|',r['extra'].get('severity'),'|',m.get('cwe') if not isinstance(m.get('cwe'),list) else m['cwe'][0][:40],'|',m.get('owasp') if not isinstance(m.get('owasp'),list) else m['owasp'][0][:30])
