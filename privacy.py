"""
KVKK (Law No. 6698) data minimization: pixelate workers' faces before an image
leaves the machine (cloud VLA API) or is stored in the episode dataset.

Uses OpenCV's YuNet face detector (models/face_detection_yunet_2023mar.onnx, MIT license).
"""
import os
import cv2
import numpy as np
from typing import List, Tuple

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "models", "face_detection_yunet_2023mar.onnx")


class FaceAnonymizer:
    def __init__(self, enabled: bool = True, score_threshold: float = 0.6):
        self.enabled = enabled
        self.detector = None
        if enabled:
            if not os.path.exists(MODEL_PATH):
                print(f"Uyarı: {MODEL_PATH} bulunamadı, KVKK yüz bulanıklaştırması devre dışı.")
                self.enabled = False
            else:
                self.detector = cv2.FaceDetectorYN.create(MODEL_PATH, "", (320, 320), score_threshold)

    def _detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        if faces is None:
            return []
        return [tuple(int(v) for v in f[:4]) for f in faces]

    def anonymize(self, frame: np.ndarray) -> Tuple[np.ndarray, int]:
        """Return a copy of the frame with every detected face pixelated, and the face count."""
        if not self.enabled:
            return frame, 0

        faces = self._detect(frame)
        if not faces:
            return frame, 0

        out = frame.copy()
        height, width = out.shape[:2]
        for (x, y, w, h) in faces:
            # Grow the box a little so hair line and chin are covered too
            pad_w, pad_h = w // 5, h // 5
            x1, y1 = max(0, x - pad_w), max(0, y - pad_h)
            x2, y2 = min(width, x + w + pad_w), min(height, y + h + pad_h)
            if x2 <= x1 or y2 <= y1:
                continue
            region = out[y1:y2, x1:x2]
            small = cv2.resize(region, (8, 8), interpolation=cv2.INTER_LINEAR)
            out[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
        return out, len(faces)
