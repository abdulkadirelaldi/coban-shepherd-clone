"""
Vision Capture Module for capturing frames via OpenCV
"""
import os
import cv2
import time
import numpy as np
from typing import Optional, Tuple


class VisionCapture:
    def __init__(self, camera_index: int = 0, resolution: Tuple[int, int] = (640, 480)):
        """
        Initialize the camera. The requested resolution is only a hint:
        the real frame size is always read from the captured frame.
        """
        self.camera_index = camera_index
        self.requested_resolution = resolution
        self.cap = cv2.VideoCapture(camera_index)

        if not self.cap.isOpened():
            print(f"Uyarı: {camera_index} numaralı kamera açılamadı.")
        else:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
            # Warm up the camera (auto exposure / white balance)
            time.sleep(1)

    def is_opened(self) -> bool:
        return self.cap.isOpened()

    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single, fresh frame from the camera."""
        if not self.cap.isOpened():
            print("Hata: Kamera başlatılmamış.")
            return None

        # Flush stale frames from the driver buffer
        for _ in range(5):
            self.cap.grab()

        ret, frame = self.cap.read()
        if not ret or frame is None:
            print("Hata: Kameradan kare okunamadı.")
            return None

        return frame

    @staticmethod
    def frame_size(frame: np.ndarray) -> Tuple[int, int]:
        """Return the actual (width, height) of a frame."""
        height, width = frame.shape[:2]
        return width, height

    @staticmethod
    def frame_to_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
        """Compress the frame to JPEG bytes."""
        ok, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("JPEG sıkıştırma başarısız.")
        return buffer.tobytes()

    @staticmethod
    def save_debug_frame(frame: np.ndarray, pixel: Tuple[int, int], label: str, path: str) -> None:
        """Save a copy of the frame with the predicted target point drawn on it."""
        annotated = frame.copy()
        cv2.drawMarker(annotated, pixel, (0, 0, 255), cv2.MARKER_CROSS, 30, 2)
        cv2.putText(annotated, label, (pixel[0] + 10, max(pixel[1] - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        cv2.imwrite(path, annotated)

    def release(self):
        """Release the camera resource."""
        if self.cap.isOpened():
            self.cap.release()
            print("Kamera kapatıldı.")
