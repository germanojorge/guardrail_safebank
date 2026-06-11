# Building Rigorously With an LLM Pair-Programmer

## When this applies

Any task where you (the LLM) author multiple of: spec, implementation, fixtures, tests. Most acute for **detection / validation / filtering / security** code — anywhere the question "did we catch the bad thing?" matters.

Less relevant for: small bug fixes, refactors of existing tested code, infrastructure config, UI tweaks. Use judgment — if the user is doing a 5-line edit, don't drag in this entire framework.

## The root failure mode

When the same agent writes the spec, the keywords/rules, the fixtures, and the matcher, all four converge on a single mental model. Tests then pass because they validate **consistency with the implementation**, not **correctness against reality**. This is the **closed validation loop**, and it is the dominant defect pattern of LLM-assisted greenfield work.

Every rule below exists to break that loop.

---

## Rules

### 1. Test cases must come from a different source than the implementation

**Why:** If you author both the matcher and the fixtures in the same flow, you unconsciously pick fixtures the matcher catches. The test proves internal consistency, not correctness. A fixture that literally contains a substring from your keyword list is the canonical symptom.

**How to apply:**
- Before writing a detector/validator/matcher, write the test cases first. Do not let yourself peek at how you'd implement matching.
- Prefer public benchmarks over hand-crafted fixtures whenever they exist: JailbreakBench, HarmBench, MITRE ATLAS (security); BEIR, MS MARCO (RAG); RealToxicityPrompts (toxicity); HELM (general LLM eval).
- If hand-crafting is unavoidable, draft fixtures in a session/turn where the implementation isn't loaded in context, or ask the user to provide adversarial examples from outside your conversation.
- When you spot a fixture-keyword direct match, name it: "this test is tautological — it only proves substring matching works".

### 2. Adversarial review is a required gate, not a phase to skip when busy

**Why:** Construction time always expands to fill the schedule. Without a budgeted destruction slot, defects only surface in external review — which for any deadline project means too late.

**How to apply:**
- Before declaring a feature done, spend a fixed slice (10–20% of build time) attempting to break it.
- Concretely: enumerate ≥10 inputs that *should* be caught and run them through the real pipeline. Expect to find ≥3 misses — if you don't, your coverage is shallow, not your detector strong.
- Standard bypass families to always try: **encoding** (base64, leet, whitespace, unicode lookalikes), **paraphrase** (synonyms, translation, indirection), **negation** ("not X" containing X), **context smuggling** (instruction inside quoted text, code block, JSON field).

### 3. 100% pass on first run is a warning, not a celebration

**Why:** Real detection code rarely works on attempt one. All-green either means the tests are tautological with the implementation, or the coverage is too narrow to expose anything. Treat green-on-first-try as a signal to dig deeper, not to merge.

**How to apply:**
- When tests pass on first try, your next action is "what would break this?", not "ship it".
- Compare your numbers to published research on the same problem. If you're outperforming SOTA with a weekend project, you're measuring the wrong thing.

### 4. Document drift is lying — fix the doc in the same change

**Why:** ADRs, READMEs, specs, and design docs decay silently. The next reader (reviewer, teammate, future-you) reads the doc first and forms expectations the code can't meet. The gap between "what the doc promises" and "what the code does" is where credibility dies.

**How to apply:**
- If you change behavior in a way that contradicts an ADR/spec/README, **update the doc in the same commit**. Not "later", not "next sprint".
- If you'd be embarrassed to show an external reviewer the doc-vs-code diff today, that's the gap to close before moving on.
- When the user asks "what does this do?", read the code, not the doc — and flag any mismatch you notice.

### 5. Question the success criterion, not just whether you met it

**Why:** A criterion written in a planning doc can be the wrong thing to optimize. "Blocks all adversarial fixtures" is meaningless if you wrote the fixtures to match the matcher. Meeting a bad criterion feels like progress and isn't.

**How to apply:**
- Periodically re-derive: "what would a skeptical external reviewer (or the actual end user) care about?" — not "what does my checklist say".
- If you can't translate a passing test into "we'd catch X in production with input Y from source Z", the test isn't validating anything real.

### 6. Substring matching against a finite list is almost never a guardrail

**Why:** Hand-curated keyword lists fail to every paraphrase and encoding, and over-fire on common substrings appearing in unrelated context. They produce a false sense of coverage that's hard to distinguish from real coverage in passing tests.

**How to apply:**
- If you reach for `if needle in haystack` as the only detection layer, treat it as a fast-path placeholder, never as the load-bearing check.
- Real detection uses validators (Presidio, spaCy NER, classifier models), checksums (Luhn, document-ID digits), or LLM judges with explicit rubric — usually layered.
- When time forces keyword-only matching, name the function `_fast_path_*`, write the limitation into a `LIMITATIONS.md`, and note it in the next handoff.

### 7. Be explicit about known limitations — don't hide them

**Why:** A reviewer (interview, code review, postmortem) respects "I know v1 has these specific gaps, here is the roadmap" infinitely more than "look at my 100% pass rate". Honesty about limits is a senior signal; pretending coverage you don't have is a junior signal.

**How to apply:**
- Maintain a `LIMITATIONS.md` (or equivalent section) listing what your system *reliably misses* — not hypothetical edge cases, real classes of bypass you've confirmed.
- Mark known-failing tests as `xfail` with `reason=` pointing to the limitations doc, instead of deleting them.
- When presenting work, surface limitations **before** the reviewer notices them. Pre-emptive honesty is uncostly; defensive backpedaling under questioning is expensive.

### 8. Volume of artifact is not rigor

**Why:** Spec frameworks, ADRs, contracts, data-models, plan templates — these coordinate work, they don't validate it. A project drowning in structured documentation can still produce broken code that passes its own tests. The feeling of thoroughness from filling templates is not the same thing as actual thoroughness.

**How to apply:**
- After producing a structured artifact (plan, spec, ADR), ask: "what concrete, automatable check would catch me lying in this doc?" If none exists, the artifact is decoration, not validation.
- Prefer one externally-validated check over five aspirational docs.
- If a tool's main output is more documents, treat its outputs with extra skepticism — the tool measures completion of itself, not progress on the problem.

---

## When in doubt, two heuristics

- **"Could I prove this works to someone who actively wants to find a flaw?"** If no, the work isn't done.
- **"Are my tests measuring what the user/reviewer cares about, or what's convenient to measure?"** If you can't answer cleanly, re-derive the criterion before writing more code.

---

## What to do when these rules conflict with deadline pressure

They will. The cost is real (≈20% build slowdown from rule 1 + rule 2 alone). The defense is: **the cost is paid up-front in time; the alternative is paid later in credibility, with interest**. For interview / demo / customer-facing work, the credibility cost dominates. For throwaway prototypes, relax these rules consciously and label the artifact as throwaway.

When you must skip a rule, **say so explicitly to the user** ("I'm skipping adversarial review on this because X — flagging so you can decide"). Silent skipping is the failure mode that compounds.
