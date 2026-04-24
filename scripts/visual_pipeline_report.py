import argparse
import csv
import html
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


sys.path.append("/workspace/droid/scripts")

from openpi_droid_main import (  # noqa: E402
    build_camera_kwargs,
    extract_observation,
    make_observation_source,
    make_policy_client,
    make_policy_request,
    process_action,
    save_preview_image,
    validate_action_chunk,
    validate_policy_request,
)


ACTION_NAMES = [
    "joint_0",
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
    "gripper",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Create a visual no-motion report for the DROID/OpenPI pipeline.")
    parser.add_argument("--output_dir", default="/workspace/reports/openpi_droid_visual_report")
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--open_loop_horizon", type=int, default=8)
    parser.add_argument("--left_camera_id", default=os.environ.get("DROID_VARIED_CAMERA_1_ID", "arducam_left"))
    parser.add_argument("--right_camera_id", default=os.environ.get("DROID_VARIED_CAMERA_2_ID", ""))
    parser.add_argument("--wrist_camera_id", default=os.environ.get("DROID_HAND_CAMERA_ID", "d435_color"))
    parser.add_argument("--external_camera", choices=["left", "right"], default="left")
    parser.add_argument("--camera_backend", default=os.environ.get("DROID_CAMERA_BACKEND", "openpi"))
    parser.add_argument("--left_camera_device", default=os.environ.get("DROID_ARDUCAM_LEFT_DEVICE"))
    parser.add_argument("--right_camera_device", default=os.environ.get("DROID_ARDUCAM_RIGHT_DEVICE"))
    parser.add_argument("--d435_serial", default=os.environ.get("DROID_D435_SERIAL"))
    parser.add_argument("--camera_width", type=int, default=0)
    parser.add_argument("--camera_height", type=int, default=0)
    parser.add_argument("--camera_fps", type=int, default=30)
    parser.add_argument("--mock_cameras", action="store_true")
    parser.add_argument("--mock_robot_state", action="store_true", default=True)
    parser.add_argument("--real_robot_state", dest="mock_robot_state", action="store_false")
    parser.add_argument("--mock_policy", action="store_true")
    parser.add_argument("--mock_policy_bad_shape", action="store_true")
    parser.add_argument("--remote_host", default=os.environ.get("OPENPI_HOST", "127.0.0.1"))
    parser.add_argument("--remote_port", type=int, default=int(os.environ.get("OPENPI_PORT", "8000")))
    parser.add_argument("--prompt", default=os.environ.get("OPENPI_PROMPT") or "visual pipeline report")
    parser.add_argument("--no_bgr_to_rgb", action="store_true")
    parser.add_argument("--no_launch_robot", action="store_true")
    parser.add_argument("--no_reset", action="store_true", default=True)
    parser.add_argument("--save_preview", default="")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.external_camera == "right" and not args.right_camera_id:
        raise ValueError("--external_camera=right requires --right_camera_id")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    policy_client = make_policy_client(args)
    observation_source = make_observation_source(args)
    action_rows = []
    report_rows = []
    pred_action_chunk = None
    actions_from_chunk_completed = 0

    try:
        for step_idx in range(args.steps):
            obs_dict = observation_source.get_observation()
            curr_obs = extract_observation(args, obs_dict, save_to_disk=False)

            camera_panel = output_dir / "camera_panel_{0:03d}.png".format(step_idx)
            save_preview_image(camera_panel, [curr_obs["left_image"], curr_obs["wrist_image"], curr_obs["right_image"]])
            save_source_images(output_dir, step_idx, curr_obs)

            request_data = None
            if (
                pred_action_chunk is None
                or actions_from_chunk_completed >= args.open_loop_horizon
                or actions_from_chunk_completed >= pred_action_chunk.shape[0]
            ):
                actions_from_chunk_completed = 0
                request_data = make_policy_request(curr_obs, args.external_camera, args.prompt)
                validate_policy_request(request_data)
                save_policy_images(output_dir, step_idx, request_data)
                pred_action_chunk = np.asarray(policy_client.infer(request_data)["actions"])
                validate_action_chunk(pred_action_chunk)

            raw_action = pred_action_chunk[actions_from_chunk_completed]
            processed_action = process_action(raw_action)
            actions_from_chunk_completed += 1

            append_action_rows(action_rows, step_idx, raw_action, processed_action)
            report_rows.append(
                {
                    "step": step_idx,
                    "camera_panel": camera_panel.name,
                    "chunk_shape": tuple(pred_action_chunk.shape),
                    "raw_min": float(np.min(raw_action)),
                    "raw_max": float(np.max(raw_action)),
                    "processed_min": float(np.min(processed_action)),
                    "processed_max": float(np.max(processed_action)),
                    "policy_refreshed": request_data is not None,
                }
            )

        actions_csv = output_dir / "actions.csv"
        write_actions_csv(actions_csv, action_rows)
        raw_plot = output_dir / "raw_action_plot.png"
        processed_plot = output_dir / "processed_action_plot.png"
        save_action_plot(raw_plot, action_rows, prefix="raw")
        save_action_plot(processed_plot, action_rows, prefix="processed")
        report_path = output_dir / "report.html"
        write_html_report(report_path, args, report_rows, actions_csv.name, raw_plot.name, processed_plot.name)
    finally:
        observation_source.close()

    print("visual_report_ok {0}".format(output_dir / "report.html"))


def save_policy_images(output_dir, step_idx, request_data):
    for key, filename in [
        ("observation/exterior_image_1_left", "policy_external_{0:03d}.png"),
        ("observation/wrist_image_left", "policy_wrist_{0:03d}.png"),
    ]:
        Image.fromarray(np.asarray(request_data[key], dtype=np.uint8)).save(output_dir / filename.format(step_idx))


def save_source_images(output_dir, step_idx, curr_obs):
    for key, filename in [
        ("left_image", "source_left_{0:03d}.png"),
        ("wrist_image", "source_wrist_{0:03d}.png"),
        ("right_image", "source_right_{0:03d}.png"),
    ]:
        image = curr_obs.get(key)
        if image is not None:
            Image.fromarray(np.asarray(image, dtype=np.uint8)).save(output_dir / filename.format(step_idx))


def append_action_rows(action_rows, step_idx, raw_action, processed_action):
    for kind, action in [("raw", raw_action), ("processed", processed_action)]:
        row = {"step": step_idx, "kind": kind}
        for idx, value in enumerate(np.asarray(action).tolist()):
            row[ACTION_NAMES[idx]] = float(value)
        action_rows.append(row)


def write_actions_csv(path, action_rows):
    fieldnames = ["step", "kind"] + ACTION_NAMES
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(action_rows)


def save_action_plot(path, action_rows, prefix):
    rows = [row for row in action_rows if row["kind"] == prefix]
    width, height = 980, 520
    margin_left, margin_top, margin_right, margin_bottom = 80, 34, 26, 80
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    draw.rectangle(
        [margin_left, margin_top, margin_left + plot_w, margin_top + plot_h],
        outline=(190, 190, 190),
        width=1,
    )
    draw.text((margin_left, 10), "{0} action trace".format(prefix), fill=(20, 20, 20), font=font)

    for y_value in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        y = value_to_y(y_value, margin_top, plot_h)
        color = (180, 180, 180) if y_value == 0 else (230, 230, 230)
        draw.line([(margin_left, y), (margin_left + plot_w, y)], fill=color, width=1)
        draw.text((8, y - 6), "{0:.1f}".format(y_value), fill=(80, 80, 80), font=font)

    colors = [
        (215, 48, 39),
        (252, 141, 89),
        (254, 224, 144),
        (145, 191, 219),
        (69, 117, 180),
        (102, 189, 99),
        (166, 97, 26),
        (118, 42, 131),
    ]
    steps = [row["step"] for row in rows]
    max_step = max(max(steps), 1) if steps else 1

    for action_idx, name in enumerate(ACTION_NAMES):
        points = []
        for row in rows:
            x = margin_left + int((row["step"] / max_step) * plot_w)
            y = value_to_y(row[name], margin_top, plot_h)
            points.append((x, y))
        if len(points) == 1:
            x, y = points[0]
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=colors[action_idx])
        elif len(points) > 1:
            draw.line(points, fill=colors[action_idx], width=2)
        legend_x = margin_left + (action_idx % 4) * 220
        legend_y = height - 56 + (action_idx // 4) * 22
        draw.rectangle([legend_x, legend_y, legend_x + 14, legend_y + 10], fill=colors[action_idx])
        draw.text((legend_x + 20, legend_y - 2), name, fill=(20, 20, 20), font=font)

    image.save(path)


def value_to_y(value, margin_top, plot_h):
    clipped = max(-1.0, min(1.0, float(value)))
    return margin_top + int((1.0 - ((clipped + 1.0) / 2.0)) * plot_h)


def write_html_report(path, args, report_rows, actions_csv, raw_plot, processed_plot):
    rows_html = "\n".join(
        "<tr><td>{step}</td><td>{chunk_shape}</td><td>{raw_min:.3f}</td><td>{raw_max:.3f}</td>"
        "<td>{processed_min:.3f}</td><td>{processed_max:.3f}</td><td>{policy_refreshed}</td>"
        "<td><img src='{camera_panel}'></td></tr>".format(**row)
        for row in report_rows
    )
    body = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>DROID/OpenPI Visual Pipeline Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #222; }}
    img {{ max-width: 720px; height: auto; border: 1px solid #ccc; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f3f3; }}
    code {{ background: #f4f4f4; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>DROID/OpenPI Visual Pipeline Report</h1>
  <p><strong>Prompt:</strong> {prompt}</p>
  <p><strong>Policy:</strong> {policy}</p>
  <p><strong>Cameras:</strong> left={left}, wrist={wrist}, right={right}</p>
  <p><a href="{actions_csv}">actions.csv</a></p>
  <h2>Action Plots</h2>
  <p><img src="{raw_plot}"></p>
  <p><img src="{processed_plot}"></p>
  <h2>Steps</h2>
  <table>
    <tr>
      <th>Step</th><th>Chunk</th><th>Raw min</th><th>Raw max</th>
      <th>Processed min</th><th>Processed max</th><th>Policy refreshed</th><th>Camera panel</th>
    </tr>
    {rows}
  </table>
</body>
</html>
""".format(
        prompt=html.escape(args.prompt),
        policy="mock" if args.mock_policy else "{0}:{1}".format(args.remote_host, args.remote_port),
        left=html.escape(str(args.left_camera_id)),
        wrist=html.escape(str(args.wrist_camera_id)),
        right=html.escape(str(args.right_camera_id or "disabled")),
        actions_csv=html.escape(actions_csv),
        raw_plot=html.escape(raw_plot),
        processed_plot=html.escape(processed_plot),
        rows=rows_html,
    )
    path.write_text(body)


if __name__ == "__main__":
    main()
