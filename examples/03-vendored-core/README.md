# 03 — core vendored into the .yak (scenario D)

The same `ringkit` core as example 02, but shipped **inside** the package:
`GHUSER_YAK_INCLUDE: "src/ringkit:lib/ringkit"`. The component's first lines find
`<packages>/<rhino>/rccn-ringkit-vendored/{{version}}/lib` and add it to `sys.path`.
No registry and no pip setup. Users install one file.

```bash
scripts/ghuser --yak rccn-ringkit-vendored --yak-include src/ringkit:lib/ringkit
```

Limits (pure Python only; restart Rhino after an update) and what still needs checking
on a real machine: [docs/deploy-scenarios.md › D](../../docs/deploy-scenarios.md#d-lab-tool-core-vendored-into-the-yak).
