import argparse
import os
import sys
from types import SimpleNamespace

import numpy as np
import torch


sys.path.append("/workspace/droid/scripts")

from openpi_droid_main import (  # noqa: E402
    MockPolicyClient,
    make_policy_request,
    process_action,
    validate_action_chunk,
)


RESET_JOINTS = np.array([0, -1 / 5 * np.pi, 0, -4 / 5 * np.pi, 0, 3 / 5 * np.pi, 0.0])
MAX_GRIPPER_WIDTH = 0.08


class FakeRobotModel:
    def forward_kinematics(self, joint_positions):
        return torch.tensor([0.45, 0.0, 0.35]), torch.tensor([0.0, 0.0, 0.0, 1.0])


class FakePolymetisRobot:
    def __init__(self):
        self.robot_model = FakeRobotModel()
        self.joint_positions = RESET_JOINTS.astype(float).copy()
        self.joint_updates = []
        self.started_cartesian_impedance = 0

    def get_robot_state(self):
        return SimpleNamespace(
            joint_positions=self.joint_positions.tolist(),
            joint_velocities=[0.0] * 7,
            joint_torques_computed=[0.0] * 7,
            prev_joint_torques_computed=[0.0] * 7,
            prev_joint_torques_computed_safened=[0.0] * 7,
            motor_torques_measured=[0.0] * 7,
            prev_controller_latency_ms=0.0,
            prev_command_successful=True,
            timestamp=SimpleNamespace(seconds=0, nanos=0),
        )

    def get_joint_positions(self):
        return torch.tensor(self.joint_positions)

    def is_running_policy(self):
        return True

    def start_cartesian_impedance(self):
        self.started_cartesian_impedance += 1

    def update_desired_joint_positions(self, command):
        command_np = command.detach().cpu().numpy()
        if command_np.shape != (7,):
            raise ValueError("Expected 7D joint command, got {0}".format(command_np.shape))
        if not np.isfinite(command_np).all():
            raise ValueError("Joint command contains non-finite values")
        self.joint_updates.append(command_np.copy())
        self.joint_positions = command_np.astype(float)


class FakePolymetisGripper:
    def __init__(self):
        self.width = MAX_GRIPPER_WIDTH
        self.goto_calls = []

    def get_state(self):
        return SimpleNamespace(width=self.width)

    def goto(self, width, speed, force, blocking=False):
        if not np.isfinite(width):
            raise ValueError("Gripper width is non-finite")
        if width < -1e-9 or width > MAX_GRIPPER_WIDTH + 1e-9:
            raise ValueError("Gripper width out of range: {0}".format(width))
        self.width = float(np.clip(width, 0.0, MAX_GRIPPER_WIDTH))
        self.goto_calls.append(
            {
                "width": self.width,
                "speed": float(speed),
                "force": float(force),
                "blocking": bool(blocking),
            }
        )


def parse_args():
    parser = argparse.ArgumentParser(description="No-motion smoke test for VLA actions through DROID FrankaRobot.")
    parser.add_argument("--mock_policy", action="store_true", help="Use a local synthetic OpenPI-like action chunk.")
    parser.add_argument("--remote_host", default=os.environ.get("OPENPI_HOST", "127.0.0.1"))
    parser.add_argument("--remote_port", type=int, default=int(os.environ.get("OPENPI_PORT", "8000")))
    parser.add_argument("--prompt", default="no-motion VLA action path test")
    parser.add_argument("--steps", type=int, default=8)
    return parser.parse_args()


def main():
    args = parse_args()
    action_chunk = get_action_chunk(args)
    validate_action_chunk(action_chunk)

    fake_robot, fake_gripper, droid_robot = make_fake_franka_robot()
    max_abs_joint_step = 0.0

    for idx, raw_action in enumerate(action_chunk[: args.steps]):
        processed_action = process_action(raw_action)
        if processed_action.shape != (8,):
            raise ValueError("Processed action must be 8D, got {0}".format(processed_action.shape))

        before = fake_robot.joint_positions.copy()
        action_info = droid_robot.update_command(
            processed_action,
            action_space="joint_velocity",
            gripper_action_space="position",
            blocking=False,
        )
        after = fake_robot.joint_positions.copy()
        max_abs_joint_step = max(max_abs_joint_step, float(np.max(np.abs(after - before))))

        required_keys = {"joint_position", "joint_velocity", "gripper_position", "robot_state"}
        missing = sorted(required_keys.difference(action_info))
        if missing:
            raise ValueError("Action info missing keys: {0}".format(missing))

    if len(fake_robot.joint_updates) != min(args.steps, action_chunk.shape[0]):
        raise RuntimeError("Not all actions reached fake update_desired_joint_positions")
    if len(fake_gripper.goto_calls) != len(fake_robot.joint_updates):
        raise RuntimeError("Not all actions reached fake gripper.goto")

    print(
        "vla_action_path_ok chunk={0} executed={1} joint_updates={2} gripper_gotos={3} "
        "max_abs_joint_step={4:.4f} final_gripper_width={5:.4f}".format(
            action_chunk.shape,
            len(fake_robot.joint_updates),
            len(fake_robot.joint_updates),
            len(fake_gripper.goto_calls),
            max_abs_joint_step,
            fake_gripper.width,
        )
    )


def get_action_chunk(args):
    if args.mock_policy:
        request = make_synthetic_request(args.prompt)
        return np.asarray(MockPolicyClient().infer(request)["actions"])

    from openpi_client import websocket_client_policy

    request = make_synthetic_request(args.prompt)
    client = websocket_client_policy.WebsocketClientPolicy(args.remote_host, args.remote_port)
    return np.asarray(client.infer(request)["actions"])


def make_synthetic_request(prompt):
    curr_obs = {
        "left_image": np.zeros((480, 640, 3), dtype=np.uint8),
        "wrist_image": np.zeros((480, 640, 3), dtype=np.uint8),
        "joint_position": RESET_JOINTS.astype(np.float32),
        "gripper_position": np.array([0.0], dtype=np.float32),
    }
    return make_policy_request(curr_obs, "left", prompt)


def make_fake_franka_robot():
    import droid.franka.robot as franka_robot_module
    from droid.franka.robot import FrankaRobot
    from droid.robot_ik.robot_ik_solver import RobotIKSolver

    # Make the nonblocking DROID path deterministic for a smoke test.
    franka_robot_module.run_threaded_command = lambda command, args=(), daemon=True: command(*args)

    fake_robot = FakePolymetisRobot()
    fake_gripper = FakePolymetisGripper()
    droid_robot = FrankaRobot.__new__(FrankaRobot)
    droid_robot._robot = fake_robot
    droid_robot._gripper = fake_gripper
    droid_robot._max_gripper_width = MAX_GRIPPER_WIDTH
    droid_robot._ik_solver = RobotIKSolver()
    droid_robot._controller_not_loaded = False
    return fake_robot, fake_gripper, droid_robot


if __name__ == "__main__":
    main()
