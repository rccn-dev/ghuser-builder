# ghuser-builder: package Grasshopper .ghuser components on Linux -- no Windows, no Rhino.
#
#   docker build -t ghuser-builder .
#   docker run --rm -v "$PWD:/work" -w /work ghuser-builder ghuser-build components dist
#
# The componentizer is Python, but it writes .ghuser files through GH_IO.dll, the
# .NET library Grasshopper uses to save files. Mono runs that assembly on Linux.
#
# Everything that decides whether a .ghuser loads in a user's Rhino is pinned
# here and recorded as an image label, so an image tag names one exact toolchain.

# Pinned by digest: the build is reproducible, and CI's layer cache stays valid
# until this line changes. Bump deliberately (README, "What is pinned"):
#   docker buildx imagetools inspect debian:bookworm-slim
FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587

# mono-devel, not mono-runtime: pythonnet needs the netstandard facade, which
# Debian ships only in mono-devel. libmonosgen is the runtime pythonnet hosts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        mono-devel libmonosgen-2.0-1 \
        python3 python3-pip curl unzip zip ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

ARG PYTHONNET_VERSION=3.0.3
RUN pip3 install --no-cache-dir --break-system-packages "pythonnet==${PYTHONNET_VERSION}"
ENV PYTHONNET_RUNTIME=mono \
    PYTHONNET_MONO_LIBMONO=/usr/lib/libmonosgen-2.0.so.1

# GH_IO.dll from the official Grasshopper NuGet package. A .ghuser written by a
# newer GH_IO than the user's Rhino will not load, so this is a decision, not "latest".
ARG GH_VERSION=8.35.26251.13001
RUN mkdir -p /opt/ghio \
    && curl -fsSL "https://www.nuget.org/api/v2/package/Grasshopper/${GH_VERSION}" -o /tmp/gh.nupkg \
    && unzip -j /tmp/gh.nupkg 'lib/net48/GH_IO.dll' -d /opt/ghio \
    && rm /tmp/gh.nupkg

# The COMPAS componentizer (MIT, Gramazio Kohler Research), pinned. Only the
# CPython variant (Rhino 8 script components): componentize_ipy.py is written to
# run under IronPython on Windows and does not run on CPython + Mono.
ARG COMPONENTIZER_SHA=dfec7e4fdb16add832793c1d5715287532841430
RUN mkdir -p /opt/componentizer \
    && curl -fsSL "https://raw.githubusercontent.com/compas-dev/compas-actions.ghpython_components/${COMPONENTIZER_SHA}/componentize_cpy.py" \
        -o /opt/componentizer/componentize_cpy.py

COPY tools/ /opt/ghuser-builder/tools/
COPY bin/ghuser-build /usr/local/bin/ghuser-build
RUN chmod +x /usr/local/bin/ghuser-build

LABEL org.opencontainers.image.title="ghuser-builder" \
      org.opencontainers.image.description="Build, verify and package Grasshopper .ghuser components on Linux" \
      dev.rccn.ghuser.gh_version="${GH_VERSION}" \
      dev.rccn.ghuser.componentizer_sha="${COMPONENTIZER_SHA}" \
      dev.rccn.ghuser.pythonnet="${PYTHONNET_VERSION}"

ENV GHUSER_GH_VERSION=${GH_VERSION} \
    GHUSER_COMPONENTIZER_SHA=${COMPONENTIZER_SHA}

WORKDIR /work
# No ENTRYPOINT: CI systems (GitLab `image:`, GitHub `container:`) need a shell.
CMD ["ghuser-build", "--help"]
