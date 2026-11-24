"""The sanity check after the agent has finished (M2-7). It is not the verify step (M2-8).

It asks one question: does the regression test the agent wrote at least pass on the fixed copy, and
do a few of Juice Shop's own server specs still pass? It runs inside the sandbox through a function
the caller gives (the SDK's workspace command call), so no Docker and no network are needed here.
No model is involved. It does not prove the fix works. It only stops a visibly broken fix from
becoming a pull request.
"""
import re
from dataclasses import dataclass, field

WORKDIR = "/workspace/app"
SPEC = "test/server/loginSqlInjectionSpec.ts"            # the file the agent is told to create
EXISTING = ["test/server/insecuritySpec.ts", "test/server/currentUserSpec.ts"]  # Juice Shop's own specs
TIMEOUT_SECONDS = 180
TAIL_LINES = 40


@dataclass
class SanityResult:
    ok: bool = False
    reasons: list = field(default_factory=list)
    passing: int = 0
    failing: int = 0
    output_tail: str = ""

    def as_dict(self):
        return {"ok": self.ok, "reasons": self.reasons, "passing": self.passing,
                "failing": self.failing, "output_tail": self.output_tail}


def parse_mocha(output):
    """(passing, failing) from mocha's summary lines."""
    passing = sum(int(n) for n in re.findall(r"^\s*(\d+) passing", output, re.MULTILINE))
    failing = sum(int(n) for n in re.findall(r"^\s*(\d+) failing", output, re.MULTILINE))
    return passing, failing


def _mocha(*files):
    return f"cd {WORKDIR} && npx mocha -r tsx " + " ".join(files)


def _tail(text, scrub):
    for s in scrub:
        if s:
            text = text.replace(s, "***")
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def run_sanity(execute, scrub=()):
    """execute(command, timeout) returns (exit_code, output). scrub: strings to blank out of any output kept."""
    result = SanityResult()
    try:
        code, _ = execute(f"test -f {WORKDIR}/{SPEC}", 30)
        if code != 0:
            result.reasons.append(f"the regression test file is missing ({SPEC})")
            return result

        code, out = execute(_mocha(SPEC), TIMEOUT_SECONDS)
        passing, failing = parse_mocha(out)
        result.output_tail = _tail(out, scrub)
        result.passing, result.failing = passing, failing
        if code != 0 or failing:
            result.reasons.append(f"the regression test failed (exit {code}, {failing} failing)")
        elif passing < 1:
            result.reasons.append("the regression test file has no passing test")

        code, out = execute(_mocha(*EXISTING), TIMEOUT_SECONDS)
        p2, f2 = parse_mocha(out)
        result.passing += p2
        result.failing += f2
        if code != 0 or f2:
            result.reasons.append(f"an existing Juice Shop spec failed (exit {code}, {f2} failing)")
            result.output_tail = _tail(out, scrub)
    except Exception as e:  # a timeout or a lost connection is a failed check, not a crash
        result.reasons.append(f"the check could not run ({type(e).__name__})")
        return result
    result.ok = not result.reasons
    return result
