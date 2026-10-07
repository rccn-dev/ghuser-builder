# 02 — component + core library (scenario C, or B)

```
src/ringkit/            the core: pure Python, no Rhino, Python 3.9-compatible
tests/                  pytest; CI runs it under Python 3.9 (Rhino 8's CPython)
components/RingPoints/  the adapter: `# r: ringkit=={{version}}`, then one call
```

A tag `v1.2.3` releases **both** `ringkit 1.2.3` (to the lab GitLab's PyPI registry)
and `rccn-ringkit-1.2.3-rh8_0-any.yak` whose component pins `ringkit==1.2.3`.

```bash
uv run --python 3.9 pytest                # the core, as CI tests it
scripts/ghuser --yak rccn-ringkit         # the components
```

Deploy: [docs/deploy-scenarios.md › C](../../docs/deploy-scenarios.md#c-lab-tool-private-registry-on-the-lab-gitlab);
for open source change `GHUSER_PYPI` to `pypi` ([› B](../../docs/deploy-scenarios.md#b-open-source-public-pypi--public-yak)).
