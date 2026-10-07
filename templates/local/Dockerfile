# Build without bind mounts -- for CI that cannot mount the workspace into a
# container (act on macOS, some Docker-in-Docker setups). Results come out
# through BuildKit, never through a shared folder:
#
#   docker build -f Dockerfile.ghuser --target export --output type=local,dest=dist .
#
# Copy to the project root as Dockerfile.ghuser; set the image to the version you pin.

FROM git.rccn.dev:5050/libs/ghuser-builder:1.0.0 AS build
ARG GHUSER_VERSION=""
ARG GHUSER_YAK_NAME=""
COPY . /work
RUN GHUSER_VERSION="$GHUSER_VERSION" GHUSER_YAK_NAME="$GHUSER_YAK_NAME" ghuser-build components /out

FROM scratch AS export
COPY --from=build /out/ /
