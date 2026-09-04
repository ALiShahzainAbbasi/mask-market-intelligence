# Web module rules

Read the root AGENTS.md and docs/MODULARITY.md first.

- Keep src/app files focused on route/layout composition, data loading, and route-level states.
- Add product screens under src/features/<feature> with their own components, clients, hooks, and tests.
- Keep components/ui reusable and presentation-only. Avoid a global catch-all hooks/services/utils layer.
- Prefer Server Components for server data/session boundaries; use small Client Components for interaction.
- Keep server credentials and provider SDKs out of client imports and public environment variables.
- Use generated contracts and runtime validation at the API boundary. Never calculate research scores or enforce authorization solely in the browser.
- Preserve the existing small health-only page until a real feature justifies extracting it.
- Run web tests, ESLint, Prettier check, strict types, and build after relevant changes.
