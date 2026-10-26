# Core r02 independent review disposition

GLM: 25,311 bytes, SHA256 07ddc55d20d8a58c7e5409897c038bbbf994aa6a7b006f27676ce55d2cb7e800.
DeepSeek: 58,942 bytes, SHA256 be3eae882bc404a22a79674f9ce08ed111e427cdbfec968e38e67fe7c36a770c.
Both source reports and the r02 ZIP remain unchanged. This is the author's decision,
not an independent acceptance of the next candidate.

| Finding | Decision |
|---|---|
| DS P2-1 baseline escape/corruption | Accept; extend real containment to named baseline reads and writes; require object + findings array of objects; normalize malformed JSON/UTF-8 and IO errors. |
| DS P2-2 surrogate filename | Accept; UnicodeError in input monitoring is INPUTS_UNAVAILABLE/exit2, with no completion marker. No lossy identity conversion. |
| DS P2-3 / GLM P2 output leaks | Accept; sanitize scan md and gate/diff successful output and saved projections, including legacy data. Core computations use original identities. |
| DS P2-4 skipped verdict | Accept the gap; core legacy pass is not MCP verdict. Correct only misleading tools_ok counts, keeping its boolean and exit semantics. Service T10 must test all/partial skipped and explicit disabled tools -> runtime gap/cannot_judge, subject to trusted quality failure precedence. |
| DS P3-1 coverage bytes | Accept incorrect claim. Keep existing adapter redaction; narrow guarantee to preserving the adapter's final sanitized bytes at the scan publication boundary. Add tests exercising the actual PytestCovAdapter producer. No claim of analyzer byte identity. |
| DS P3-2 Bearer prose | Accept; require a token signal for standalone Bearer, while header credentials retain context-based protection. Record narrower detection boundary and increment redaction rules. |
| DS P3-3 baseline writes | Fix adjacent name/device/length validation, containment, atomic save and IO mapping while already modifying baseline boundary. Preserve overwrite-by-name CLI behavior. |
| DS P3-4 baseline comparability / GLM same-name | Keep service responsibility; old named baselines are self-contained historical data without publication/comparability proof. MCP must reject run/baseline ambiguity (T13), reload source run when needed, and never infer comparability from baseline payload alone. |
| DS P3-5 gitignore | Disclose exact supported subset; do not alter target selection in this review-fix batch. Relative directory and slash-glob limitations remain. |
| DS P3-6 prefix with escaping link | Keep fail-closed behavior, disclose coarse availability. No silent selection around an escaping candidate. |
| DS P3-7 summary directory | Accept; existing non-file summary is INVALID_ARTIFACT, not ordinary IO failure. |
| DS P3-8 coverage directory | Accept; absent means nonexistent, not present-but-non-file. Reject invalid dependency before publishing a marker. |
| DS P3-9 empty failed run | Retain failed run directory/ID; do not erase evidence or reuse collision identities. Error must be structured and no marker published. |
| DS P3 old run names | Keep declared single-ID contract; old names outside ASCII/length/device limits are not newly promised compatible. |
| GLM P3 suppress --reapply invalid UTF-8 | Defer non-MCP write-tool hardening; record as known debt. No permission to modify formal .cq is inferred. |
| GLM P3 directory symlink scope | Disclose os.walk(followlinks=False) directory-symlink omission; file-link containment is a distinct rule. No full analyzer-read coverage claim. |

The three confirmed public-path defects are fixed in core rather than delegated to an
unimplemented service. MCP lifecycle/verdict/ambiguity tests remain explicit future work.
No threshold, finding severity, quality predicate or gate/diff exit policy changes.
