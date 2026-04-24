import argparse
import json
import os
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Capture the real robot state in read-only mode.")
    parser.add_argument("--output_dir", default="/workspace/reports/real_robot_state")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--sleep_s", type=float, default=0.1)
    return parser.parse_args()


def main():
    args = parse_args()
    os.environ.setdefault("DROID_ROBOT_READONLY", "1")
    os.environ.setdefault("DROID_SKIP_GRIPPER_LAUNCH", "1")
    os.environ.setdefault("DROID_MOCK_GRIPPER_POSITION", "0.0")

    from droid.franka.robot import FrankaRobot

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    robot = FrankaRobot()
    state = None
    timestamps = None
    try:
        robot.launch_controller()
        robot.launch_robot()
        for _ in range(max(1, args.samples)):
            state, timestamps = robot.get_robot_state()
            time.sleep(max(0.0, args.sleep_s))
    finally:
        robot.kill_controller()

    payload = {
        "joint_positions": state["joint_positions"],
        "cartesian_position": state["cartesian_position"],
        "gripper_position": state["gripper_position"],
        "timestamps": timestamps,
    }

    json_path = output_dir / "real_robot_state.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    rest_pose = "[" + ",".join("{:.10f}".format(float(x)) for x in state["joint_positions"]) + "]"
    env_path = output_dir / "real_robot_state.env"
    env_path.write_text("POLYMETIS_SIM_REST_POSE='{0}'\n".format(rest_pose))

    print("real_robot_state_ok {0}".format(json_path))
    print("POLYMETIS_SIM_REST_POSE={0}".format(rest_pose))


if __name__ == "__main__":
    main()
