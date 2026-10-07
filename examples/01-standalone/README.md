# 01 — standalone component (scenario A)

One component, `Spiral`, that needs nothing but Rhino. The `.ghuser`/`.yak` is the
whole tool.

```bash
scripts/ghuser --yak rccn-spiral          # with templates/local/ghuser copied to scripts/
```

CI: [`.gitlab-ci.yml`](.gitlab-ci.yml) includes the template and sets `GHUSER_YAK_NAME`.
Deploy: [docs/deploy-scenarios.md › A](../../docs/deploy-scenarios.md#a-components-only).
