import os

from droid.camera_utils.wrappers.multi_camera_wrapper import MultiCameraWrapper


def main():
    camera_ids = [
        os.environ.get("DROID_VARIED_CAMERA_1_ID", "arducam_left"),
        os.environ.get("DROID_VARIED_CAMERA_2_ID", "arducam_right"),
        os.environ.get("DROID_HAND_CAMERA_ID", "d435_color"),
    ]
    wrapper = MultiCameraWrapper(
        {
            "camera_backend": os.environ.get("DROID_CAMERA_BACKEND", "openpi"),
            "camera_ids": camera_ids,
            "default": {
                "image": True,
                "depth": False,
                "pointcloud": False,
                "concatenate_images": False,
                "resolution": (0, 0),
                "resize_func": None,
            },
        }
    )
    try:
        obs, timestamps = wrapper.read_cameras()
        print("camera image keys:", sorted(obs.get("image", {}).keys()))
        for key, frame in sorted(obs.get("image", {}).items()):
            print("{0}: shape={1} dtype={2}".format(key, frame.shape, frame.dtype))
        print("timestamp keys:", sorted(timestamps.keys()))
    finally:
        wrapper.disable_cameras()


if __name__ == "__main__":
    main()
