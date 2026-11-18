# Implementation Plan: {Feature Name}

> **Goal**: {One sentence goal}
> **Status**: Draft
> **Created**: {Today's date}

---

## Problem Statement

### Current State
{What exists today}

### Desired State
{What we want to achieve}

---

## Design Decisions

### Decision 1: {Topic}
**Context**: {Why needed}
**Options Considered**:
1. **{Option A}** - {pros/cons}
2. **{Option B}** - {pros/cons}
**Decision**: {Choice}
**Rationale**: {Why}

{Repeat for each decision}

---

## Architecture

### File Structure
```
{module or feature folder, following the project's layout}
├── {layer}/
└── {layer}/
```

### Key Interfaces
```{language}
{Core types and interfaces}
```

---

## Specification Breakdown

<!-- One spec = one commit. Keep each spec small enough to review and implement in one sitting. -->

| ID | Title | Priority | Depends On |
|----|-------|----------|------------|
| SPEC-001 | {Entity} | P0 | — |
| SPEC-002 | {Repository} | P0 | SPEC-001 |
| SPEC-003 | {Impl} | P1 | SPEC-002 |
| SPEC-004 | {UI} | P1 | SPEC-003 |

### Lanes (advisory)

<!-- Advisory only: /speclane:init re-derives lanes from depends_on and enforces the lane rules
     (see the work-item README template). A lane is the specs one worker implements in sequence;
     lanes run one at a time, in dependency order. -->

| Lane | Specs (in order) | Depends on lanes |
|------|------------------|------------------|
| A | SPEC-001, SPEC-002, SPEC-003 | — |
| B | SPEC-004 | A |

---

## Execution Order

```
Lane A: SPEC-001 → SPEC-002 → SPEC-003
       │
       ▼
Lane B: SPEC-004
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| {Risk 1} | {Strategy} |

---

## Success Criteria

- [ ] All specs complete
- [ ] Tests passing
- [ ] Static analysis clean
- [ ] Code review passed
