# BDD Feature Specifications

This directory contains Gherkin `.feature` files that serve as the
**single source of truth** for behavioral specifications.

## Who Creates Features
- **Design agent** writes `.feature` files during Phase A (journey discovery)
- **User** reviews and approves features before coding begins

## Who Implements Step Definitions
- **Backend agent** implements pytest-bdd steps in `tests/bdd/steps/`
- **Frontend agent** implements playwright-bdd steps in `frontend/e2e/steps/`

## Conventions
- Tag each feature with `@J{NNN}` matching the journey ID
- Tag priorities: `@P1`, `@P2`, `@P3`
- Tag runners: `@smoke`, `@regression`, `@frontend-only`, `@api-only`
- See: `~/.claude/docs/design-ideas/bdd-contract-testing-methodology.md`
