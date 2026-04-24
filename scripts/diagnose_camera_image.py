import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def parse_args():
    parser = argparse.ArgumentParser(description="Capture and diagnose a V4L2/OpenCV camera image.")
    parser.add_argument("--device", default="/dev/video6")
    parser.add_argument("--output_dir", default="/workspace/reports/arducam_diagnostics")
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--fourcc", default="")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stats_lines = []
    stats_lines.append(run_v4l2(["--all", "-d", args.device]))
    stats_lines.append(run_v4l2(["--list-formats-ext", "-d", args.device]))

    frame = capture_opencv_frame(args, convert_rgb=True)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb).save(output_dir / "opencv_bgr_to_rgb.png")
    Image.fromarray(frame).save(output_dir / "opencv_bgr_saved_as_rgb_wrong.png")
    stats_lines.append(format_stats("opencv_bgr", frame))
    stats_lines.append(format_stats("opencv_bgr_to_rgb", rgb))

    raw_result = capture_raw_yuyv(args)
    if raw_result is not None:
        raw, raw_rgb = raw_result
        stats_lines.append("raw shape={0} dtype={1} min={2} mean={3:.2f} max={4}".format(
            raw.shape, raw.dtype, int(raw.min()), float(raw.mean()), int(raw.max())
        ))
        if raw_rgb is not None:
            stats_lines.append(format_stats("raw_yuyv_to_rgb", raw_rgb))
            Image.fromarray(raw_rgb).save(output_dir / "raw_yuyv_to_rgb.png")

    policy_like = resize_with_pad(rgb, 224, 224)
    Image.fromarray(policy_like).save(output_dir / "policy_like_224.png")
    stats_lines.append(format_stats("policy_like_224", policy_like))

    write_contact_sheet(output_dir)
    write_html(output_dir, stats_lines)
    (output_dir / "stats.txt").write_text("\n\n".join(stats_lines))

    print("camera_diagnostics_ok {0}".format(output_dir / "report.html"))


def capture_opencv_frame(args, convert_rgb=True):
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError("Failed to open {0}".format(args.device))
    configure_cap(cap, args)
    frames = []
    for _ in range(args.frames):
        ok, frame = cap.read()
        if ok and frame is not None:
            frames.append(frame.copy())
    cap.release()
    if not frames:
        raise RuntimeError("No frames captured from {0}".format(args.device))
    return frames[-1]


def capture_raw_yuyv(args):
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        return None
    configure_cap(cap, args)
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    raw_frames = []
    for _ in range(max(2, args.frames // 2)):
        ok, raw = cap.read()
        if ok and raw is not None:
            raw_frames.append(raw.copy())
    cap.release()
    if not raw_frames:
        return None
    raw = raw_frames[-1]
    try:
        raw_rgb = cv2.cvtColor(raw, cv2.COLOR_YUV2RGB_YUY2)
    except cv2.error:
        return raw, None
    return raw, raw_rgb


def configure_cap(cap, args):
    if args.width and args.height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if args.fps:
        cap.set(cv2.CAP_PROP_FPS, args.fps)
    if args.fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))


def format_stats(name, image):
    image = np.asarray(image)
    flat = image.reshape(-1, image.shape[-1])
    mean = flat.mean(axis=0)
    std = flat.std(axis=0)
    channel_range = flat.max(axis=0) - flat.min(axis=0)
    green_dominance = float(mean[1] / max(1.0, (mean[0] + mean[2]) / 2.0))
    return (
        "{name}\n"
        "  shape={shape} dtype={dtype}\n"
        "  min={minv} mean={mean} max={maxv} std={std}\n"
        "  channel_range={channel_range} green_dominance={green_dominance:.3f}"
    ).format(
        name=name,
        shape=image.shape,
        dtype=image.dtype,
        minv=flat.min(axis=0).tolist(),
        mean=mean.round(2).tolist(),
        maxv=flat.max(axis=0).tolist(),
        std=std.round(2).tolist(),
        channel_range=channel_range.tolist(),
        green_dominance=green_dominance,
    )


def resize_with_pad(image, width, height):
    pil = Image.fromarray(np.asarray(image, dtype=np.uint8))
    scale = min(width / pil.width, height / pil.height)
    resized = pil.resize((max(1, round(pil.width * scale)), max(1, round(pil.height * scale))))
    canvas = Image.new("RGB", (width, height), "black")
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return np.asarray(canvas)


def write_contact_sheet(output_dir):
    names = [
        "opencv_bgr_saved_as_rgb_wrong.png",
        "opencv_bgr_to_rgb.png",
        "raw_yuyv_to_rgb.png",
        "policy_like_224.png",
    ]
    tiles = []
    font = ImageFont.load_default()
    for name in names:
        path = output_dir / name
        if not path.exists():
            continue
        image = Image.open(path).convert("RGB")
        image.thumbnail((320, 220))
        tile = Image.new("RGB", (320, 250), "white")
        tile.paste(image, ((320 - image.width) // 2, 0))
        draw = ImageDraw.Draw(tile)
        draw.text((5, 230), name, fill=(0, 0, 0), font=font)
        tiles.append(tile)
    if not tiles:
        return
    sheet = Image.new("RGB", (320 * len(tiles), 250), "white")
    for idx, tile in enumerate(tiles):
        sheet.paste(tile, (320 * idx, 0))
    sheet.save(output_dir / "contact_sheet.png")


def write_html(output_dir, stats_lines):
    escaped = "\n\n".join(stats_lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    images = "\n".join(
        "<h2>{0}</h2><img src='{0}'>".format(name)
        for name in [
            "contact_sheet.png",
            "opencv_bgr_to_rgb.png",
            "raw_yuyv_to_rgb.png",
            "policy_like_224.png",
        ]
        if (output_dir / name).exists()
    )
    (output_dir / "report.html").write_text(
        """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Camera Diagnostics</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; }}
    img {{ max-width: 960px; border: 1px solid #ccc; }}
    pre {{ background: #f6f6f6; padding: 12px; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>Camera Diagnostics</h1>
  {images}
  <h2>Stats</h2>
  <pre>{stats}</pre>
</body>
</html>
""".format(images=images, stats=escaped)
    )


def run_v4l2(args):
    try:
        return subprocess.check_output(["v4l2-ctl"] + args, text=True, stderr=subprocess.STDOUT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return "v4l2-ctl failed: {0}".format(exc)


if __name__ == "__main__":
    main()
