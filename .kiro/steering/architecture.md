---
inclusion: manual
---

# Skill: Architecture

## Purpose
Choose and enforce structure that keeps change cheap: high cohesion, low coupling, one-way dependencies, invariants owned by exactly one place.

## Core Rules
- **Monolith first.** Modular monolith with clear internal boundaries; extract services only when independent deploy/scale pain is proven, one service at a time, along existing module seams.
- **Organize by feature/domain, not by kind.** `orders/` containing model+service+api+tests beats `models/`+`services/`+`controllers/`.
- **Dependencies point one way**: transport/UI → domain → infrastructure/utils. The domain layer imports neither HTTP nor ORM specifics. Cycles are design bugs.
- **Deep modules, narrow interfaces.** Hide substantial complexity behind a small API. Expose the minimum; hiding later is nearly impossible.
- **Adapters at every external boundary.** One interface you own per vendor (payments, LLM, email, storage); exactly one file imports the vendor SDK; vendor errors translated into your error types at the boundary.
- **Decision weight ∝ reversibility.** Schemas, wire formats, and public APIs get design review; internal code shapes get decided fast and changed freely.
- **Make illegal states unrepresentable**: enums for status, explicit state machines for entities with transition rules, value objects (Money, EmailAddress, DateRange) over primitives, newtype IDs so entity IDs can't be swapped.
- **Composition root DI.** Pass collaborators in via constructors/params; wire the graph at startup; no service locators, no reach-out globals. Inject exactly what tests must fake: clock, RNG, network, DB.
- **Cross-cutting concerns centralized**: auth, logging, transactions, retries live in middleware/decorators, never copy-pasted into handlers.

## When to Split
- Split a file when it has two independent reasons to change or a subset is independently imported — never for line count alone.
- Split a module when its one-sentence description needs "and".
- Split a service when two teams need independent deploy cadences — not before.

## Repository & Service Patterns
- Services: stateless use-case orchestrators (validate → load → domain logic → persist → emit). One use case per method, named after the use case.
- Repositories: only when persistence needs faking/swapping or queries deserve names; return domain objects, never rows; skip when the ORM already is the repository.

## Checklist
- [ ] Can a newcomer state each module's job in one sentence?
- [ ] Grep the vendor SDK import — does it appear outside its adapter?
- [ ] Any two components sharing mutable state? Who owns it?
- [ ] Which decisions here are irreversible? Were they given proportionate care?
- [ ] Could each layer be tested with the layer below faked?

## Anti-Patterns
God objects; anemic domain + fat "managers"; premature microservices; circular imports; util landfills; framework-fighting; inner-platform effect; DI frameworks in codebases that don't already use one.
