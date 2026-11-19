"""S11: similarity match on Semgrep findings. Standard library only. Thrown away.
Reads /out/semgrep.json and the source in /src/juice-shop (read only).
Never prints a snippet for the secret finding (lib/insecurity.ts)."""
import json, re, sys, difflib, itertools, csv

import os
CTX = int(os.environ.get("CTX", "3"))
SECRET_FILES = {"lib/insecurity.ts"}
KEYWORDS = set("""const let var return if else for while function async await new try catch throw
class import export from default typeof instanceof in of this null undefined true false do switch
case break continue yield void delete""".split())
SQLWORDS = set("select from where and or like order by group limit join insert update delete union null is not in".split())
TOK = re.compile(r"""
 (?P<lc>//[^\n]*) | (?P<bc>/\*.*?\*/) |
 (?P<tpl>`(?:\\.|\$\{[^}]*\}|[^`\\])*`) |
 (?P<str>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*") |
 (?P<num>\d+(?:\.\d+)?) | (?P<id>[A-Za-z_$][\w$]*) |
 (?P<p>=>|===|!==|==|!=|<=|>=|&&|\|\||\?\?|\.\.\.|[^\s\w])
""", re.X | re.S)

def tokens(text, variant):
    out = []
    for m in TOK.finditer(text):
        k = m.lastgroup; v = m.group()
        if k in ("lc", "bc"): continue
        if k == "tpl":
            if variant == "A": out.append("STR")
            else:  # B: keep SQL words, mark each interpolation
                inner = v[1:-1]
                for part in re.split(r"(\$\{[^}]*\})", inner):
                    if part.startswith("${"): out.append("PH")
                    else: out += [w for w in re.findall(r"[a-z]+", part.lower()) if w in SQLWORDS]
                out.append("TPL")
        elif k == "str": out.append("STR")
        elif k == "num": out.append("NUM")
        elif k == "id":
            if variant == "C" or v in KEYWORDS: out.append(v)
            else: out.append("ID")
        else: out.append(v)
    return out

def shingles(t, k=3): return {tuple(t[i:i+k]) for i in range(max(1, len(t)-k+1))}
def jacc(a, b): return len(a & b) / len(a | b) if (a | b) else 0.0
def ratio(a, b): return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()

def window(path, s, e):
    try: lines = open("/src/juice-shop/" + path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError: return ""
    return "\n".join(lines[max(0, s-1-CTX): e+CTX])

def load():
    d = json.load(open("/out/semgrep.json")); by = {}
    for r in d["results"]:
        key = (r["path"], r["start"]["line"])
        f = by.setdefault(key, {"path": key[0], "line": key[1], "end": r["end"]["line"], "rules": set(), "cwe": set()})
        f["rules"].add(r["check_id"].split(".")[-1])
        cw = r["extra"].get("metadata", {}).get("cwe") or []
        cw = [cw] if isinstance(cw, str) else cw
        f["cwe"] |= {c.split(":")[0] for c in cw}
        f["end"] = max(f["end"], r["end"]["line"])
    fs = sorted(by.values(), key=lambda f: (f["path"], f["line"]))
    for f in fs:
        f["id"] = f"{f['path']}:{f['line']}"
        f["win"] = window(f["path"], f["line"], f["end"])
    return fs

def score(a, b):
    row = {}
    for v in "ABC":
        ta, tb = tokens(a["win"], v), tokens(b["win"], v)
        row["J"+v] = jacc(shingles(ta), shingles(tb)); row["R"+v] = ratio(ta, tb)
    return row

if __name__ == "__main__":
    fs = load()
    print("# findings (location, rules, CWE, window tokens in variant A)")
    for f in fs:
        print(f["id"], sorted(f["rules"]), sorted(f["cwe"]), len(tokens(f["win"], "A")))
    if "--show-norm" in sys.argv:
        for f in fs:
            if f["path"] in SECRET_FILES: continue
            if f["id"] in ("routes/login.ts:34", "routes/search.ts:23"):
                print("\n##", f["id"], "A:", " ".join(tokens(f["win"], "A")), "\nB:", " ".join(tokens(f["win"], "B")))
    print("\n# pairs")
    w = csv.writer(sys.stdout)
    w.writerow(["a", "b", "same_rule", "same_cwe", "JA", "RA", "JB", "RB", "JC", "RC"])
    for a, b in itertools.combinations(fs, 2):
        s = score(a, b)
        w.writerow([a["id"], b["id"], int(bool(a["rules"] & b["rules"])), int(bool(a["cwe"] & b["cwe"]))] + [f"{s[k]:.3f}" for k in ("JA","RA","JB","RB","JC","RC")])
