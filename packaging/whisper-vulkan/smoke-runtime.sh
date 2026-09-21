#!/usr/bin/env bash
set -euo pipefail

mode=${1:?usage: smoke-runtime.sh cpu|noicd|vulkan}
: "${OUT_DIR:=work/out}"
: "${FIXTURE_SOURCE:=vendor/whisper.cpp}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$(realpath "$OUT_DIR")"
FIXTURE_SOURCE="$(realpath "$FIXTURE_SOURCE")"
asset=whisper-bin-ubuntu-vulkan-x64
case "$mode" in
  cpu) dockerfile=Dockerfile.runtime-cpu; image=dikte-whisper-runtime-cpu:spike ;;
  noicd) dockerfile=Dockerfile.runtime-noicd; image=dikte-whisper-runtime-noicd:spike ;;
  vulkan) dockerfile=Dockerfile.runtime-vulkan; image=dikte-whisper-runtime-vulkan:spike ;;
  *) echo "unknown mode: $mode" >&2; exit 2 ;;
esac

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tar -xzf "$OUT_DIR/$asset.tar.gz" -C "$tmp"
docker build --pull=false -f "$SCRIPT_DIR/$dockerfile" -t "$image" "$SCRIPT_DIR"

args=("/bundle/$asset/whisper-server" -m /fixtures/model.bin
      --host 127.0.0.1 --port 8080
      --inference-path /v1/audio/transcriptions -l auto -sns -nlp)
env_args=()
# No -ng anywhere: Dikte passes it only when its GPU setting is off, so the
# run that has to survive a missing loader or a missing device is this one,
# where the backend registry actually goes looking for them.
if [[ "$mode" == vulkan ]]; then
  env_args=(-e LIBGL_ALWAYS_SOFTWARE=1
            -e VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.x86_64.json)
fi

docker run --rm --name "dikte-whisper-$mode-smoke" \
  -e SMOKE_MODE="$mode" \
  "${env_args[@]}" \
  -v "$tmp/$asset:/bundle/$asset:ro" \
  -v "$FIXTURE_SOURCE/models/for-tests-ggml-base.en.bin:/fixtures/model.bin:ro" \
  -v "$FIXTURE_SOURCE/samples/jfk.wav:/fixtures/jfk.wav:ro" \
  "$image" bash -ec '
    if [ "$SMOKE_MODE" = cpu ] && ldconfig -p | grep -q libvulkan.so.1; then
      echo "CPU smoke image unexpectedly has a Vulkan loader" >&2
      exit 1
    fi
    if [ "$SMOKE_MODE" = noicd ]; then
      if ! ldconfig -p | grep -q libvulkan.so.1; then
        echo "no-ICD smoke image has no Vulkan loader to load" >&2
        exit 1
      fi
      if compgen -G "/usr/share/vulkan/icd.d/*.json" >/dev/null; then
        echo "no-ICD smoke image has a driver after all" >&2
        exit 1
      fi
    fi
    "$@" >/tmp/server.log 2>&1 &
    pid=$!
    trap "kill $pid 2>/dev/null || true" EXIT
    for _ in $(seq 1 120); do
      kill -0 "$pid" 2>/dev/null || { cat /tmp/server.log; exit 1; }
      if curl --silent --show-error --fail --max-time 180 \
          -F file=@/fixtures/jfk.wav -F response_format=json \
          http://127.0.0.1:8080/v1/audio/transcriptions >/tmp/response.json; then
        grep -q "\"text\"" /tmp/response.json
        if [ "$SMOKE_MODE" = vulkan ]; then
          grep -q "loaded Vulkan backend" /tmp/server.log
        fi
        cat /tmp/response.json
        cat /tmp/server.log
        exit 0
      fi
      sleep 1
    done
    cat /tmp/server.log
    exit 1
  ' bash "${args[@]}"
