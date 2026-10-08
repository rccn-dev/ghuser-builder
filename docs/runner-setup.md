# Runner for image builds (`image-build`)

Only the `image:build` job of this repo needs it. Rootless BuildKit builds the
image without a Docker daemon, but it needs Linux **user namespaces**, which
Docker's default seccomp and AppArmor profiles block inside a container. This
runner relaxes exactly those two profiles. It is **not privileged**: the job
gets no access to the host's devices or Docker daemon.

Every other job (tests, consumer projects' builds) keeps using the ordinary
runner. This runner takes only jobs tagged `image-build`.

Time: about 10 minutes. You need Maintainer on `libs/ghuser-builder` (or Owner
on the `libs` group) and a shell on the machine that runs `rccn-docker-runner`.

---

## 1. Create the runner in GitLab

**Project runner** (only this repo can use it, recommended):
`libs/ghuser-builder` → **Settings → CI/CD → Runners** → **New project runner**.
(For the whole group instead: `libs` → **Build → Runners → New group runner**.)

| Field | Value |
| --- | --- |
| Operating systems | Linux |
| Tags | `image-build` |
| Run untagged jobs | **off** |
| Runner description | `rccn-image-build` |
| Protected | optional: on = only runs for protected branches/tags (main, `v*`), so merge requests can't build images |
| Lock to current projects | on |
| Maximum job timeout | `1800` (30 min; a build takes about 3) |

Click **Create runner**. GitLab shows a **runner authentication token**
(`glrt-…`) and a register command. **Copy the token now**: it is shown once.
Treat it like a password and don't paste it into chat, issues or commits.

## 2. Check the host allows user namespaces

On the runner host:

```bash
sysctl user.max_user_namespaces                    # must be > 0
sysctl kernel.unprivileged_userns_clone 2>/dev/null # Debian: must be 1 (absent = fine)
sysctl kernel.apparmor_restrict_unprivileged_userns 2>/dev/null   # Ubuntu 23.10+, see below
```

If the last one exists and is `1` (Ubuntu 24.04 default), Ubuntu blocks
unprivileged user namespaces even for unconfined containers. Either allow them:

```bash
echo 'kernel.apparmor_restrict_unprivileged_userns=0' | sudo tee /etc/sysctl.d/60-userns.conf
sudo sysctl --system
```

or skip ahead and use `privileged = true` for this runner only (step 3, last note).

## 3. Register it on the runner host

Find out how the existing runner is installed:

```bash
docker ps --format '{{.Names}}  {{.Image}}' | grep -i runner   # in a container?
systemctl status gitlab-runner 2>/dev/null | head -3            # or as a service?
```

**Runner in a container** (the usual setup; replace `gitlab-runner` with the
container name from `docker ps`):

```bash
docker exec -it gitlab-runner gitlab-runner register \
  --non-interactive \
  --url https://git.rccn.dev \
  --token glrt-PASTE-TOKEN-HERE \
  --name rccn-image-build \
  --executor docker \
  --docker-image alpine:3.20 \
  --docker-security-opt seccomp=unconfined \
  --docker-security-opt apparmor=unconfined
```

**Runner as a system service:** the same command without `docker exec -it gitlab-runner`,
run with `sudo`.

Tags, "run untagged" and locking were set in step 1. With `glrt-` tokens they
live in GitLab, not in the command. The register command appends a second
`[[runners]]` entry to the same `config.toml`; the existing runner is untouched
and the runner process picks up the change by itself, with no restart.

The new entry should look like this (`docker exec gitlab-runner cat /etc/gitlab-runner/config.toml`):

```toml
[[runners]]
  name = "rccn-image-build"
  url = "https://git.rccn.dev"
  token = "glrt-…"
  executor = "docker"
  [runners.docker]
    image = "alpine:3.20"
    privileged = false
    security_opt = ["seccomp=unconfined", "apparmor=unconfined"]
```

If the existing runner's entry has settings this one also needs, copy them
over and keep `privileged = false`. Typical ones: `network_mode`, `dns`, an
internal CA under `[runners.docker]`, or `clone_url`. A job that can't reach
git.rccn.dev usually means one of these is missing.

Last resort, if step 2 cannot be changed: set `privileged = true` in this entry
only (and drop `security_opt`). It works, but a privileged job is root on the
host, so keep this runner locked to this project and protected.

## 4. Check it

```bash
docker exec gitlab-runner gitlab-runner verify      # "is valid" for rccn-image-build
```

In GitLab, **Settings → CI/CD → Runners** shows `rccn-image-build` with a green
dot and the tag `image-build`. Then **Build → Pipelines → Run pipeline** on
`main`, or retry the failed `image:build` job.

A good `image:build` log ends with `pushing manifest for …:sha-<commit>`. Then
`test:examples` runs on the standard runner, inside the image just pushed.

## Troubleshooting

| `image:build` log says | Cause | Fix |
| --- | --- | --- |
| job stays *pending*: "no active runners … tags image-build" | runner not registered, offline, or tag differs | step 4; the tag must be exactly `image-build` (or set CI/CD variable `IMAGE_BUILD_RUNNER_TAG`) |
| `fork/exec /proc/self/exe: operation not permitted` | seccomp/AppArmor not relaxed | check `security_opt` in this runner's entry |
| `operation not permitted` despite `security_opt` | host blocks user namespaces | step 2 |
| `unauthorized` / `denied` when pushing | registry login | Container Registry enabled for the project? (Settings → General → Visibility) |
| `could not resolve host git.rccn.dev` | the new entry lacks the old runner's network settings | step 3, "copy them over" |

## Why not the alternatives

- **Privileged Docker-in-Docker on the default runner:** every job on that runner,
  including other projects', would get root on the host.
- **kaniko:** works unprivileged, but the project was archived in 2025.
- **Building on a laptop and pushing:** works, but puts releases outside CI.
