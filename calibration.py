"""
Camera -> Robot Calibration (pixel coordinates to robot workspace millimeters)

The camera looks at the flat work surface, so a single homography maps any
pixel on the table to an (x, y) position in the robot's coordinate frame.

Run this file directly to create calibration.json:
    python calibration.py
"""
import json
import os
import sys
import cv2
import numpy as np
from typing import List, Optional, Sequence, Tuple

MIN_POINTS = 4


class Calibration:
    def __init__(self, homography: np.ndarray, image_size: Tuple[int, int]):
        self.homography = np.asarray(homography, dtype=np.float64)
        self.image_size = tuple(image_size)

    @classmethod
    def from_points(cls, pixel_points: Sequence[Tuple[float, float]],
                    robot_points: Sequence[Tuple[float, float]],
                    image_size: Tuple[int, int]) -> "Calibration":
        """Compute the homography from at least 4 non-collinear point pairs."""
        if len(pixel_points) != len(robot_points):
            raise ValueError("pixel_points and robot_points must have the same length.")
        if len(pixel_points) < MIN_POINTS:
            raise ValueError(f"At least {MIN_POINTS} point pairs are required.")

        src = np.asarray(pixel_points, dtype=np.float64)
        dst = np.asarray(robot_points, dtype=np.float64)
        method = cv2.RANSAC if len(src) > MIN_POINTS else 0
        homography, _ = cv2.findHomography(src, dst, method)
        if homography is None:
            raise ValueError("Could not compute a homography. Are the points collinear?")
        return cls(homography, image_size)

    @classmethod
    def load(cls, path: str) -> Optional["Calibration"]:
        """Load a calibration file, returning None if it does not exist or is invalid."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(np.array(data["homography"]), tuple(data["image_size"]))
        except (OSError, KeyError, ValueError) as e:
            print(f"Kalibrasyon dosyası okunamadı ({path}): {e}")
            return None

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"homography": self.homography.tolist(),
                       "image_size": list(self.image_size)}, f, indent=2)

    def pixel_to_robot(self, pixel: Tuple[float, float],
                       frame_size: Optional[Tuple[int, int]] = None) -> Tuple[float, float]:
        """
        Map a pixel to robot (x, y) in mm. If the frame was captured at a
        different resolution than the calibration image, rescale it first.
        """
        px, py = pixel
        if frame_size is not None and tuple(frame_size) != self.image_size:
            px = px * self.image_size[0] / frame_size[0]
            py = py * self.image_size[1] / frame_size[1]

        src = np.array([[[px, py]]], dtype=np.float64)
        x, y = cv2.perspectiveTransform(src, self.homography)[0][0]
        return float(x), float(y)

    def mean_error(self, pixel_points, robot_points) -> float:
        """Average distance (mm) between the measured and the mapped robot points."""
        errors = [np.linalg.norm(np.subtract(self.pixel_to_robot(p), r))
                  for p, r in zip(pixel_points, robot_points)]
        return float(np.mean(errors))


def _read_robot_point(index: int) -> Optional[Tuple[float, float]]:
    while True:
        raw = input(f"Nokta {index}: robot X Y (mm, örn. '150 -40', boş = atla): ").strip()
        if not raw:
            return None
        try:
            x, y = (float(v) for v in raw.replace(",", " ").split())
            return x, y
        except ValueError:
            print("Lütfen tam olarak iki sayı girin.")


def run_interactive_calibration() -> int:
    """Click known points in a still camera frame and enter their robot coordinates."""
    from config import load_settings
    from vision_capture import VisionCapture

    settings = load_settings()
    vision = VisionCapture(settings.camera_index, (settings.camera_width, settings.camera_height))
    if not vision.is_opened():
        return 1

    print("\nMasaya, robot koordinatlarını bildiğiniz en az 4 işaret koyun")
    print("(örn. gripper ucunu bir noktaya götürün, X/Y değerini okuyun, oraya işaret koyun).")
    print("İşaretleri tüm çalışma alanına yayın. Kalibrasyondan sonra kamerayı oynatmayın.")
    input("Kalibrasyon görüntüsünü çekmek için Enter'a basın...")

    frame = vision.capture_frame()
    vision.release()
    if frame is None:
        return 1

    image_size = VisionCapture.frame_size(frame)
    pixel_points: List[Tuple[float, float]] = []
    robot_points: List[Tuple[float, float]] = []
    clicks: List[Tuple[int, int]] = []
    window = "Calibration - click a marker, 'c' = compute, 'u' = undo, 'q' = quit"

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)

    while True:
        view = frame.copy()
        for i, p in enumerate(pixel_points, start=1):
            cv2.drawMarker(view, (int(p[0]), int(p[1])), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
            cv2.putText(view, str(i), (int(p[0]) + 8, int(p[1]) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow(window, view)
        key = cv2.waitKey(30) & 0xFF

        if clicks:
            pixel = clicks.pop(0)
            robot = _read_robot_point(len(pixel_points) + 1)
            if robot is not None:
                pixel_points.append(pixel)
                robot_points.append(robot)
        elif key == ord('u') and pixel_points:
            pixel_points.pop()
            robot_points.pop()
        elif key == ord('q'):
            cv2.destroyAllWindows()
            print("Kalibrasyon iptal edildi.")
            return 1
        elif key == ord('c'):
            if len(pixel_points) < MIN_POINTS:
                print(f"En az {MIN_POINTS} nokta gerekli, şu an {len(pixel_points)} var.")
                continue
            try:
                calib = Calibration.from_points(pixel_points, robot_points, image_size)
            except ValueError as e:
                print(f"Hata: {e}")
                continue
            cv2.destroyAllWindows()
            calib.save(settings.calibration_file)
            print(f"{settings.calibration_file} kaydedildi "
                  f"(ortalama hata: {calib.mean_error(pixel_points, robot_points):.1f} mm).")
            return 0


if __name__ == "__main__":
    sys.exit(run_interactive_calibration())
