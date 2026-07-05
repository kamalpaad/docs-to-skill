"""
test_pipeline.py -- lightweight automated checks for the docs-to-skill
pipeline. No pytest dependency; run directly with:

    python test_pipeline.py

Runs entirely in mock mode (no API key / network needed), so it's safe to
run in CI or right before recording your demo video as a sanity check.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
SKILLS_DIR = ROOT / "skills"

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


# 1. Regenerate skills fresh, in mock mode, so tests are deterministic
if SKILLS_DIR.exists():
    shutil.rmtree(SKILLS_DIR, ignore_errors=True)

result = run([sys.executable, "generate_skills.py", "--mock"])
check("generate_skills.py --mock exits successfully", result.returncode == 0)

expected_skills = {"vpn-setup", "expense-reimbursement", "onboarding-checklist"}
found_skills = {p.name for p in SKILLS_DIR.iterdir()} if SKILLS_DIR.exists() else set()
check(f"generated skills for all 3 sample docs {expected_skills}", expected_skills.issubset(found_skills))

# 2. Every SKILL.md has valid frontmatter + non-empty body
import re
import yaml

for name in expected_skills:
    md_path = SKILLS_DIR / name / "SKILL.md"
    check(f"{name}/SKILL.md exists", md_path.exists())
    if not md_path.exists():
        continue
    text = md_path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    check(f"{name}/SKILL.md has valid frontmatter delimiters", bool(m))
    if m:
        fm = yaml.safe_load(m.group(1)) or {}
        check(f"{name}/SKILL.md frontmatter has 'name'", "name" in fm)
        check(f"{name}/SKILL.md frontmatter has 'description'", "description" in fm)
        check(f"{name}/SKILL.md body is non-empty", len(m.group(2).strip()) > 0)
    check(f"{name}/references/source.md exists (traceability)", (SKILLS_DIR / name / "references" / "source.md").exists())

# 3. Q&A routing -- each question should cite the correct skill
qa_cases = [
    ("How do I set up VPN access on my laptop?", "vpn-setup"),
    ("What's the deadline for submitting travel expenses?", "expense-reimbursement"),
    ("When is the benefits enrollment deadline for new hires?", "onboarding-checklist"),
]
for question, expected_skill in qa_cases:
    result = run([sys.executable, "qa_agent.py", "--mock", question])
    cited_correctly = f"Cited skill: {expected_skill}" in result.stdout
    check(f"qa_agent cites '{expected_skill}' for: {question!r}", cited_correctly)

# 4. Irrelevant question should not force a false citation
result = run([sys.executable, "qa_agent.py", "--mock", "What's the weather like today?"])
check("qa_agent declines to cite a skill for an unrelated question", "Cited skill:" not in result.stdout)

print()
if failures:
    print(f"{len(failures)} check(s) FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("All checks passed.")
