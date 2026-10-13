# Docker 开发工作流

## 核心原则

容器是可重建的环境，不是工作成果的唯一存储位置：

```text
Git                  保存版本历史
Windows bind mount   保存和编辑源码
Docker named volume  保存日志、缓存或 Linux 构建产物
Dockerfile/Compose   保存环境定义
```

## 持久化工作空间

建议目录：

```text
ros-docker/
├── Dockerfile
├── compose.yaml
└── catkin_ws/
    └── src/
```

在该目录的 **PowerShell** 中执行：

```powershell
docker volume create ros1-logs

docker run --rm -it `
  --name ros1-noetic `
  -e DISPLAY=host.docker.internal:0.0 `
  -e QT_X11_NO_MITSHM=1 `
  --shm-size=1g `
  --mount "type=bind,source=$PWD\catkin_ws,target=/root/catkin_ws" `
  --mount "type=volume,source=ros1-logs,target=/root/.ros" `
  osrf/ros:noetic-desktop-full `
  bash
```

在 Windows 文件系统上编译较慢或遇到权限问题时，可以只挂载 `src/`，把 `build/`、`devel/` 放在 Linux named volume 中。

## 推荐 Dockerfile

```dockerfile
FROM osrf/ros:noetic-desktop-full

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    x11-apps \
    mesa-utils \
    netcat-openbsd \
    iproute2 \
    iputils-ping \
    usbutils \
    git \
    vim \
    nano \
    build-essential \
    python3-catkin-tools \
 && rm -rf /var/lib/apt/lists/*

RUN echo 'source /opt/ros/noetic/setup.bash' >> /root/.bashrc \
 && echo '[ -f /root/catkin_ws/devel/setup.bash ] && source /root/catkin_ws/devel/setup.bash' >> /root/.bashrc

WORKDIR /root/catkin_ws
CMD ["bash"]
```

构建：

```powershell
docker build -t ros1-noetic-dev .
```

## 推荐 Compose 配置

```yaml
services:
  ros-dev:
    build: .
    image: ros1-noetic-dev
    container_name: ros1-noetic
    stdin_open: true
    tty: true
    environment:
      DISPLAY: host.docker.internal:0.0
      QT_X11_NO_MITSHM: "1"
      ROS_MASTER_URI: http://localhost:11311
    shm_size: 1gb
    volumes:
      - ./catkin_ws:/root/catkin_ws
      - ros1-logs:/root/.ros

volumes:
  ros1-logs:
```

常用操作：

```powershell
docker compose up -d --build
docker compose exec ros-dev bash
docker compose logs -f ros-dev
docker compose down
```

`docker compose down` 会删除容器和默认网络，但不会删除上面声明的 named volume。需要删除数据卷时必须明确执行带卷删除的操作，并先确认其中没有需要保留的数据。

## catkin 工作空间

容器中首次创建：

```bash
mkdir -p ~/catkin_ws/src
cd ~/catkin_ws
catkin_make
source devel/setup.bash
```

创建包：

```bash
cd ~/catkin_ws/src
catkin_create_pkg my_robot \
  rospy roscpp std_msgs geometry_msgs sensor_msgs

cd ~/catkin_ws
catkin_make
source devel/setup.bash
```

每次新终端都必须加载 ROS 环境和工作空间环境。可以放入 `.bashrc`，但排错时仍应检查：

```bash
echo "$ROS_DISTRO"
rospack find my_robot
```

## 用户和文件权限

初学阶段可以先用 root 容器打通流程。长期开发建议在 Dockerfile 中创建普通用户，并让其 UID/GID 与工作目录的实际权限匹配。不要为了绕过权限问题直接使用 `--privileged`。

下一步：[ROS 1 基础与实践](04-ROS1基础与实践.md)

