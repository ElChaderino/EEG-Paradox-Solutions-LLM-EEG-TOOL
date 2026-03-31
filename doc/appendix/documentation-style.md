# Appendix — Documentation Style (Editorial Standard)

## Objective

Preserve clarity and maintainability of this documentation set. The standard is **engineering prose**: precise, testable statements—aligned with how Admiral Hopper’s teams specified systems: no ambiguity about what the machine shall do.

## Voice

- Use **active voice** for procedures: “The operator shall start Ollama,” not “Ollama should be started.”
- Use **shall** for normative requirements, **may** for permission, **should** for recommendation.
- Avoid marketing language and unsubstantiated superlatives.

## Structure

- Each document states an **Objective** first.
- Use tables for enumerations (config keys, tools, symptoms).
- Cross-link with relative paths: `reference/configuration.md`.

## Accuracy rule

When behavior changes in code, the author **shall** update:

1. The relevant `reference/` page.
2. `doc/README.md` map if files are added or removed.
3. Root `README.md` only if entry commands change.
4. **`CHANGELOG.md`** and root **`VERSION`** when cutting a user-visible release (use `scripts/bump_version.ps1` after editing `VERSION`).

## Terminology

Prefer terms in `glossary.md`. Define new terms on first use in a document if not in glossary.

## Formatting

- Use fenced blocks for JSON and shell only when they improve precision.
- Do not use the section symbol in user-visible headings (rendering limitations).

## Related

- `doc/README.md` — index.
