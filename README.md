# OpenPI + DROID single-PC runtime

This folder is the Docker-first runtime scaffold for one-PC DROID/OpenPI deployment:

- one container
- mounted local DROID and OpenPI checkouts
- host network
- USB/V4L2/RealSense device access
- OpenPI policy server and DROID rollout launched as separate processes

The container is intentionally permissive for hardware bring-up:

- `privileged: true`
- `/dev:/dev`
- `/dev/bus/usb:/dev/bus/usb`
- `/run/udev:/run/udev:ro`
- cgroup rules for `/dev/video*`, `/dev/ttyUSB*`, and USB bus devices

## First setup

```bash
cd /home/msabbah/Desktop/droid_openpi_runtime
cp .env.example .env
docker compose -f docker-compose.singlepc.yml build
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid /workspace/runtime_scripts/bootstrap_envs.sh
```

The bootstrap installs into named Docker volumes for `/opt/micromamba/envs`, `/opt/micromamba/pkgs`, and `/root/.cache`,
so the installed Python environments persist across `docker compose run --rm` calls.

For real Franka control, DROID also needs the FAIRO/Polymetis low-level stack and libfranka in the
robot-control env. Initialize the FAIRO source first:

```bash
git -C /home/msabbah/Desktop/droid submodule update --init --recursive droid/fairo
```

In this checkout, `.gitmodules` may exist without a registered `droid/fairo` gitlink. If the command above
fails with `pathspec did not match`, clone FAIRO directly:

```bash
git clone --recursive https://github.com/facebookresearch/fairo.git \
  /home/msabbah/Desktop/droid/droid/fairo
```

Then build the Franka stack inside the container:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/bootstrap_fairo_franka.sh
```

If you want the container to initialize or clone FAIRO itself, set `DROID_BOOTSTRAP_FAIRO_SUBMODULE=1`.
The bootstrap follows DROID's upstream path: FAIRO source repo, Polymetis runtime package, libfranka
`0.9.0` for Panda or `0.10.0` for FR3, and Polymetis built with `BUILD_FRANKA=ON`.

Edit these before hardware tests:

- `.env`
- `config/cameras.env`
- `config/robot.env`

Find camera devices with:

```bash
v4l2-ctl --list-devices
lsusb
rs-enumerate-devices
```

## Start server and rollout

Open one terminal for the policy server:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_policy_server.sh
```

Open another terminal for camera + policy dry-run:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_rollout_dry_run.sh \
  --prompt "pick up the object" \
  --mock_robot_state
```

Then dry-run with real robot state but no motion, after `bootstrap_fairo_franka.sh` passes:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_rollout_dry_run.sh \
  --prompt "pick up the object"
```

Only after dry-run succeeds, enable real motion in `.env`:

```env
DROID_ENABLE_ROBOT_MOTION=1
CONFIRM_REAL_ROBOT=1
```

Then run:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_rollout_execute.sh \
  --prompt "pick up the object" \
  --max_timesteps 600
```

## Smoke checks

Camera-only:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  micromamba run -n droid python /workspace/runtime_scripts/smoke_cameras.py
```

Gripper command dry-run:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/smoke_gripper.sh
```

FAIRO/Polymetis low-level availability:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/test_polymetis.sh
```

## Notes

- `scripts/openpi_droid_main.py` defaults to dry-run and refuses motion unless both motion guards are set.
- The policy input uses one external Arducam plus the D435 color stream.
- The D435 reader uses `pyrealsense2`; if the device is not visible, check host USB permissions, `/run/udev`, and `DROID_D435_SERIAL`.
- The Franka Hand launch command is configurable through `DROID_GRIPPER_LAUNCH_CMD`.
- The upstream repo/submodule is `fairo`, but this DROID code still imports the low-level robot runtime as `polymetis` and expects `launch_robot.py` / `launch_gripper.py`.
- Real robot rollout runs in `DROID_ROBOT_RUNTIME_ENV`, defaulting to `polymetis-local`, while the OpenPI policy server runs in the separate `openpi` env.
- The compose service is privileged, uses host networking, mounts `/dev`, `/dev/bus/usb`, and `/run/udev`, and adds `SYS_NICE` plus RT ulimits for the Franka control process.
