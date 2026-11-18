ARG ROS_BASE_IMAGE=ros:jazzy-ros-base
FROM ${ROS_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-dev-tools python3-colcon-common-extensions \
    ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
    ros-jazzy-tf2-ros-py ros-jazzy-cv-bridge \
    python3-numpy python3-opencv python3-yaml python3-pytest python3-venv \
    libosmesa6 libegl1 libgl1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Keep ROS's apt-installed Python bindings visible to MuJoCo and project code.
RUN python3 -m venv --system-site-packages /opt/robopilot-venv \
    && /opt/robopilot-venv/bin/python -m pip install --no-cache-dir 'mujoco==4.0.1'

ARG USER_UID=1006
ARG USER_GID=1006
RUN groupadd --non-unique --gid "$USER_GID" robopilot \
    && useradd --non-unique --uid "$USER_UID" --gid "$USER_GID" --create-home robopilot

COPY docker/entrypoint.sh /usr/local/bin/robopilot-entrypoint
RUN chmod 755 /usr/local/bin/robopilot-entrypoint
ENV MUJOCO_GL=osmesa ROS_DOMAIN_ID=106 ROS_LOCALHOST_ONLY=1
ENV PYTHONPATH=/workspace/RoboPilot/src/robopilot
WORKDIR /workspace/RoboPilot
USER robopilot
ENTRYPOINT ["/usr/local/bin/robopilot-entrypoint"]
CMD ["bash"]
