# API module rules

Read the root AGENTS.md, progress.txt, and docs/MODULARITY.md first.

- main.py only creates/wires FastAPI; put shared HTTP behavior in transport/.
- Feature routers must not import SQLAlchemy, ORM models, or repositories. Resolve a typed service through dependency wiring.
- Services/ports/domain modules must not import FastAPI, SQLAlchemy, the PostgreSQL
  job adapter, settings, or concrete infrastructure. Dependency interfaces should
  describe the use case, not a generic CRUD or queue framework.
- Keep the generic job queue split into pure domain/contracts, a port, the
  SQLAlchemy model/repository adapter, and composition wiring. Feature services
  depend on the port; worker handlers must not import queue models or repositories.
- Keep models/repository/wiring inside the feature that owns them. Use composite tenant foreign keys and explicit tenant-scoped queries.
- Centralize model registration in persistence/registry.py and the expected migration revision in persistence/schema.py.
- Never add unauthenticated market endpoints or treat a development smoke token as a user session.
- Follow docs/AUTHORIZATION.md for identity interfaces. AuthenticatedActor/AccessGrant are internal values, never caller-supplied credentials. Inject real verified session storage before wiring business routes; no fake runtime fallback. Keep role gates separate from tenant-scoped resource/workflow checks and transactional audit.
- New migrations must not import current ORM models. Add offline schema checks and actual PostgreSQL migration/constraint tests; offline checks alone do not close a schema checkpoint.
- Authentication for the private Windows MVP uses local accounts plus
  PostgreSQL-backed server sessions under ADR 0003. Keep password hashing,
  session storage, CSRF, bootstrap, membership authorization, and audit as narrow
  adapters/services; never accept an environment token as an end-user login.
- Preserve compatibility exports only deliberately; do not add new implementations to the old forwarding modules.
- Run the API natively on loopback for development. Integration tests must not stop shared OS services; use isolated connection-failure tests and separately documented operator restart/shutdown acceptance.
