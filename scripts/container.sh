#!/usr/bin/env bash
# User-scoped image; never install packages on the host or use its ROS workspace.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
image_name="robopilot-ros-jazzy:uid-$(id -u)"
action="${1:-shell}"
if [[ $# -gt 0 ]]; then shift; fi
case "$action" in
  build)
    docker build --file "$project_dir/docker/Dockerfile" \
      --build-arg "ROS_BASE_IMAGE=${ROS_BASE_IMAGE:-ros:jazzy-ros-base}" \
      --build-arg "USER_UID=$(id -u)" --build-arg "USER_GID=$(id -g)" \
      --tag "$image_name" "$project_dir"
    ;;
  exec)
    if [[ $# -eq 0 ]]; then set -- bash; fi
    interactive=()
    [[ -t 0 ]] && interactive+=(-i)
    [[ -t 0 && -t 1 ]] && interactive+=(-t)
    docker exec "${interactive[@]}" "robopilot-bridge-$(id -u)" \
      /usr/local/bin/robopilot-entrypoint "$@"
    ;;
  shell|run|viewer|bridge|sim)
    interactive=()
    [[ -t 0 ]] && interactive+=(-i)
    [[ -t 0 && -t 1 ]] && interactive+=(-t)
    ports=()
    name=()
    if [[ "$action" == sim ]]; then
      name=(--name "robopilot-bridge-$(id -u)")
      ports=(-p 127.0.0.1:18081:8080)
      set -- python -m robopilot.mujoco_sim "$@"
    elif [[ "$action" == bridge ]]; then
      name=(--name "robopilot-bridge-$(id -u)")
      for arg in "$@"; do
        if [[ "$arg" == --web ]]; then ports=(-p 127.0.0.1:18081:8080); fi
        if [[ "$arg" == --web-port* ]]; then
          echo 'container.sh uses fixed Web Viewer ports: server 18081 -> container 8080; omit --web-port' >&2
          exit 2
        fi
      done
      set -- python -m robopilot.mujoco_bridge "$@"
    elif [[ "$action" == viewer ]]; then
      if [[ $# -ne 1 ]]; then
        echo 'Usage: bash scripts/container.sh viewer /workspace/RoboPilot/path/to/model.xml' >&2
        exit 2
      fi
      ports=(-p 127.0.0.1:18081:8080)
      set -- python -m mujoco.studio.viewer --model="$1" --gfx=web --port=8080
    elif [[ "$action" == shell ]]; then
      set -- bash
    elif [[ $# -eq 0 ]]; then
      echo 'Usage: bash scripts/container.sh run COMMAND [ARG ...]' >&2
      exit 2
    fi
    docker run --rm --init "${interactive[@]}" \
      --cpus=4 --memory=6g --memory-swap=6g --shm-size=256m \
      --cap-drop=ALL --security-opt=no-new-privileges \
      --mount "type=bind,src=$project_dir,dst=/workspace/RoboPilot" \
      "${ports[@]}" "${name[@]}" "$image_name" "$@"
    ;;
  *) echo 'Usage: bash scripts/container.sh {build|shell|run COMMAND...|viewer MODEL|bridge|sim|exec COMMAND...}' >&2; exit 2 ;;
esac
