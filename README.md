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
./install_all.sh
```

The installer builds the image, installs the DROID/OpenPI envs, installs the FAIRO/Polymetis/libfranka
robot-control env, installs DROID's Franka configs into `/workspace/runtime_config/polymetis`, and runs
the low-level availability check.

The Python environments install into named Docker volumes for `/opt/micromamba/envs`, `/opt/micromamba/pkgs`,
and `/root/.cache`, so they persist across `docker compose run --rm` calls.

FAIRO is a git submodule at `/home/msabbah/Desktop/droid/droid/fairo`. If you ever need to repair or
refresh it manually:

```bash
git -C /home/msabbah/Desktop/droid submodule update --init --recursive droid/fairo
```

If an older checkout has `.gitmodules` metadata without a registered `droid/fairo` gitlink and the command
above fails with `pathspec did not match`, repair the gitlink:

```bash
git -C /home/msabbah/Desktop/droid submodule add --force \
  https://github.com/facebookresearch/fairo.git droid/fairo
git -C /home/msabbah/Desktop/droid submodule update --init droid/fairo
```

Then rebuild the Franka stack inside the container:

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

## Runbook: preview before live robot

Use this order before every real robot run. Replace the prompt as needed.

### 1. Start OpenPI policy server

Skip this if a policy server is already running on `127.0.0.1:8000`.

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_policy_server.sh
```

### 2. Generate a no-motion visual report

This captures real camera images, reads robot state in read-only mode, sends one or more OpenPI requests,
and writes policy images plus action plots. It does not execute robot motion.

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  micromamba run -n polymetis-local python /workspace/runtime_scripts/visual_pipeline_report.py \
    --real_robot_state \
    --no_reset \
    --prompt "grab the red cube on the table" \
    --steps 8 \
    --open_loop_horizon 8 \
    --output_dir /workspace/reports/grab_red_cube_visual_real_state
```

Open `reports/grab_red_cube_visual_real_state/report.html`.

### 3. Preview VLA motion in PyBullet

This sends real-camera OpenPI outputs to the localhost Bullet sim, not to the real robot. The sim is a
rough rejection test for obviously bad actions, not a faithful task simulator: it does not model the real
table, cube, camera geometry, or grasp contact. For the closest preview, copy the real robot's current
joint pose into the sim start pose. The first policy chunk is the best-aligned one; later chunks can drift
because the simulated robot moves while the real cameras still see the stationary real setup.

Capture the real robot state in read-only mode:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/capture_real_robot_state.sh \
    --output_dir /workspace/reports/real_robot_state

source reports/real_robot_state/real_robot_state.env
```

Allow the container to open an X11 window:

```bash
xhost +SI:localuser:root
```

Terminal 1, start the GUI sim:

```bash
docker compose -f docker-compose.singlepc.yml run --rm \
  -e DISPLAY="$DISPLAY" \
  -e QT_X11_NO_MITSHM=1 \
  -e POLYMETIS_SIM_GUI=true \
  -e POLYMETIS_SIM_REST_POSE="$POLYMETIS_SIM_REST_POSE" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  openpi-droid \
  /workspace/runtime_scripts/start_polymetis_bullet_sim.sh
```

Terminal 2, run the VLA-to-sim preview:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_rollout_sim_preview.sh \
    --prompt "grab the red cube on the table" \
    --max_timesteps 120 \
    --open_loop_horizon 8
```

Inspect `reports/sim_preview_debug/rollout.csv`, `policy_inputs/`, and `action_chunks/`. If actions
saturate, flip signs repeatedly, or the motion looks unstable, do not go live yet.
The preview warms up camera observations before the first policy call to avoid dark first-frame
auto-exposure artifacts.

Stop the rollout terminal first, then the sim terminal. The sim owns localhost ports `50051` and `50052`.
Optionally revoke X11 permission:

```bash
xhost -SI:localuser:root
```

### 4. Run a read-only dry run

This streams real cameras and OpenPI outputs while keeping robot motion disabled. The wrapper forces
read-only arm state and skips the gripper launcher.

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_rollout_dry_run.sh \
    --prompt "grab the red cube on the table" \
    --max_timesteps 30
```

### 5. Execute on the real robot

Only after the visual report, sim preview, and read-only dry run look acceptable, enable real motion in
`.env`:

```env
DROID_ENABLE_ROBOT_MOTION=1
CONFIRM_REAL_ROBOT=1
```

Then run:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_rollout_execute.sh \
    --prompt "grab the red cube on the table" \
    --max_timesteps 600
```

## Smoke checks

No-hardware OpenPI contract check:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/smoke_openpi_mock_rollout.sh
```

This uses synthetic cameras, a synthetic robot state, and a mock policy that returns an action chunk shaped
like the OpenPI DROID policy. It exercises observation extraction, request construction, image resizing,
action validation, gripper binarization, clipping, and dry-run logging without requiring robot motion,
real cameras, or a running policy server.

Camera-only:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  micromamba run -n droid python /workspace/runtime_scripts/smoke_cameras.py
```

Camera wrapper without hardware:

```bash
docker compose -f docker-compose.singlepc.yml run --rm -e DROID_CAMERA_BACKEND=mock openpi-droid \
  micromamba run -n droid python /workspace/runtime_scripts/smoke_cameras.py
```

Visual pipeline report:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  micromamba run -n droid python /workspace/runtime_scripts/visual_pipeline_report.py \
  --mock_policy --steps 1 --output_dir /workspace/reports/visual_real_cameras_mock_policy
```

Open `reports/visual_real_cameras_mock_policy/report.html` on the host to inspect camera panels,
policy-sized images, action plots, and the action CSV.

Arducam image diagnostics:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  micromamba run -n droid python /workspace/runtime_scripts/diagnose_camera_image.py \
  --device /dev/video6 --output_dir /workspace/reports/arducam_diagnostics
```

Open `reports/arducam_diagnostics/report.html` to compare OpenCV conversion, raw YUYV conversion,
the policy-sized image, and per-channel statistics.

No-motion VLA action path through DROID FrankaRobot:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  micromamba run -n polymetis-local python /workspace/runtime_scripts/smoke_vla_action_path.py --mock_policy
```

With a running OpenPI policy server, the same check can use real policy outputs while still using fake
Polymetis robot/gripper interfaces:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  micromamba run -n polymetis-local python /workspace/runtime_scripts/smoke_vla_action_path.py
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

## Optional headless sim smoke

This verifies the Polymetis sim execution path with mock cameras and a mock policy. Use the GUI preview
in the runbook above for real OpenPI motion assessment.

Terminal 1:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_polymetis_bullet_sim.sh
```

Terminal 2:

```bash
docker compose -f docker-compose.singlepc.yml run --rm openpi-droid \
  /workspace/runtime_scripts/start_rollout_sim_execute.sh \
  --mock_policy --prompt "simulation smoke test" --max_timesteps 20
```

## Notes

- `scripts/openpi_droid_main.py` defaults to dry-run and refuses motion unless both motion guards are set.
- `scripts/openpi_droid_main.py --mock_robot_state --mock_cameras --mock_policy` provides a full
  no-hardware contract check for development machines.
- The policy input uses one external Arducam plus the D435 color stream.
- The D435 reader uses `pyrealsense2`; if the device is not visible, check host USB permissions, `/run/udev`, and `DROID_D435_SERIAL`.
- The Franka Hand launch command is configurable through `DROID_GRIPPER_LAUNCH_CMD`.
- The robot launch wrapper uses `DROID_POLYMETIS_CONFIG_DIR` plus `DROID_ROBOT_CLIENT_CONFIG` and
  `DROID_ROBOT_MODEL_CONFIG` to pass Polymetis `--config-dir`, so DROID-specific Franka configs live in
  the runtime overlay instead of overwriting upstream FAIRO files.
- The upstream repo/submodule is `fairo`, but this DROID code still imports the low-level robot runtime as `polymetis` and expects `launch_robot.py` / `launch_gripper.py`.
- Real robot rollout runs in `DROID_ROBOT_RUNTIME_ENV`, defaulting to `polymetis-local`, while the OpenPI policy server runs in the separate `openpi` env.
- The compose service is privileged, uses host networking, mounts `/dev`, `/dev/bus/usb`, and `/run/udev`, and adds `SYS_NICE` plus RT ulimits for the Franka control process.
