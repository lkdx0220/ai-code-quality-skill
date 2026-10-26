# Core r01 independent review disposition

Source: GLM and DeepSeek 2026-10-25 r01 reports. This is the author's disposition,
not an independent sign-off of the next candidate. Prior packages and logs remain intact.

| Finding | Decision and implementation boundary |
|---|---|
| DS P1 schema downgrade | Accept; marker/inputs presence independently requires publication validation. Unknown or mistyped explicit versions fail closed. Genuine legacy runs remain readable. |
| DS P2-1 / P3-8 Windows identity | Accept; resolve actual filesystem spelling and use platform-native case normalization for prefix matching. |
| DS P2-2 read escape | Accept in core; validate references and real containment of audits/run/dependencies, including legacy summary/findings. |
| DS P2-3 output redaction | Accept; sanitize input display paths before hashing, add original-path SHA256 identities, bump input rules to 2 and record redaction version. Sanitize successful scan JSON too. |
| DS P2-4 adapter meaning | Accept ambiguity; keep effective_adapters as backward-compatible selection alias. Add selected/attempted/completed/skipped arrays. A skipped selected tool remains a runtime gap. |
| GLM P2-1 binary corruption | Accept; normalize UTF-8 errors and both publication verification passes at the load_run boundary. CLI consumers receive artifact errors without broad exception swallowing. |
| DS P3-1 input deadline | Accept; core summary records per-inventory inputs_timeout_seconds. Service job records total deadline/source later. |
| DS P3-2 / GLM P3-1 catch order | Accept; FileNotFoundError before OSError retains the existing missing-project exit 1. |
| DS P3-3 verification exception | Accept; both passes wrap EvidenceError as RunNotFoundError. |
| DS P3-4 coverage bytes | Accept; fsync the analyzer's completed file without text decoding or rewriting. Publication still hashes exact bytes. |
| DS P3-5 / GLM P3-8 directory fsync | Disclose; no power-loss transaction or directory fsync guarantee. Process interruption remains detectable. |
| DS P3-6 marker bytes | Disclose; marker is structured metadata, not a cryptographic signature or proof that marker bytes never changed. |
| DS P3-7 partial exact run | Accept; existing exact directories without a summary return RUN_NOT_READY. |
| DS P3-9 inventory deadline | Keep configurable 60..600 capability (CLI accepts >0..600); no claim of a universal timely scan. No 100k-file evidence claimed. |
| DS P3-10 / GLM P3-5 repeat hashing | Defer optimization; correctness first, measure and optimize service paging separately. Do not weaken verification to hide cost. |
| DS P3-11 gitignore | Keep disclosed root-only subset; monitoring set is not all analyzer reads. |
| DS P3-12 CLI docs | Accept; document new flags, compatibility and input representation in README/adapters docs. |
| GLM P3-2 Bearer prose | Accept; header-aware Basic/Bearer rules plus minimum length for standalone Bearer, with prose regression. Unknown tokens remain outside a universal detection promise. |
| GLM P3-3 Authorization | Accept; explicitly cover Basic/Bearer header forms including Proxy-Authorization. |
| GLM P3-4 external source link | Keep fail-closed OUTSIDE_PROJECT policy and document it. Silently excluding the file could misrepresent completeness. |
| GLM P3-6 JSON format | Disclose canonical compact/sorted LF gate/diff files; parsed JSON/exit behavior retained. |
| GLM P3-7 format counts | Scope clarification: src/tests previously 56; repository-wide previously 60, both passed. New counts must be measured again. |
| GLM P3-7 timing | Reject the specific claim that parsing is outside record.seconds: source assigns it after json.loads. Accept the limitation: command wall time is not internal monitoring time. Retain old evidence unchanged. |
| GLM P3-7 empty index | Accept unusable evidence; empty vscode-source-index.json proves nothing and is not relied upon. |
| GLM P3-8 permissions | Disclose POSIX atomic temporary outputs use 0600; no claim of Linux product validation from Windows tests. |

New regression coverage must target actual public failure modes, including downgrade,
binary corruption across consumers, traversal/junction, Windows aliases, redaction with
recomputable digests and colliding display names, adapter gaps, and exact coverage bytes.
Gate/diff algorithms, thresholds, formal .cq and original baseline stay unchanged.
