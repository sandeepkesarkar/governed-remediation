"""Hand-written snippets (not from any scan) to see whether a score would still link the same flaw written differently."""
import os; os.environ["CTX"] = "0"
import match
fs = {f["id"]: f for f in match.load()}
SYN = {
 "syn1 same flaw, same library, renamed": "const rows = await db.sequelize.query(`SELECT * FROM Orders WHERE owner = '${req.query.owner}'`)",
 "syn2 same flaw, other library, concatenation": 'const rows = await pool.query("SELECT * FROM accounts WHERE id = " + req.params.id)',
 "syn3 unrelated (open redirect)": "res.redirect(req.query.to)",
}
for name, code in SYN.items():
    print(name)
    for tgt in ("routes/login.ts:34", "routes/search.ts:23"):
        row = []
        for v in "ABC":
            ta, tb = match.tokens(fs[tgt]["win"], v), match.tokens(code, v)
            row.append(f"J{v}={match.jacc(match.shingles(ta), match.shingles(tb)):.3f} R{v}={match.ratio(ta, tb):.3f}")
        print("  vs", tgt, " ".join(row))
