"""
Episode Logger: the data flywheel

Every task is stored as an episode (observations + model decisions + robot
commands + outcome). Shepherd feeds the experience of deployed robots back
into training; these episodes are the same kind of dataset, ready to be used
for fine-tuning or imitation learning later.

    episodes/20261004-153012_kirmizi-kupleri-kutuya-koy/
        episode.json      # instruction, steps, outcome
        frames/step_01.jpg ...
        video.mp4         # simulation only: the whole run, with captions
"""
import json
import os
import re
import time
import cv2
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional

VIDEO_FPS = 15
_TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def ascii_tr(text: str) -> str:
    """OpenCV fonts cannot draw Turkish letters, so fold them to ASCII for captions."""
    return text.translate(_TR_ASCII)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_tr(text).lower()).strip("-")
    return slug[:max_len].rstrip("-") or "gorev"


class EpisodeLogger:
    def __init__(self, root: str, instruction: str, model: str, mode: str, record_video: bool = False):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = os.path.join(root, f"{stamp}_{slugify(instruction)}")
        os.makedirs(os.path.join(self.dir, "frames"), exist_ok=True)
        self.started = time.time()
        self.record_video = record_video
        self.caption = ascii_tr(instruction)
        self.writer: Optional[cv2.VideoWriter] = None
        self.data: Dict[str, Any] = {
            "instruction": instruction,
            "model": model,
            "mode": mode,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "steps": [],
        }

    def log_observation(self, step: int, frame: np.ndarray) -> str:
        path = os.path.join(self.dir, "frames", f"step_{step:02d}.jpg")
        cv2.imwrite(path, frame)
        # Hold the model's view for a moment so the video is easy to follow
        self.add_video_frame(frame, f"Adim {step}: kamera goruntusu modele gonderildi", repeat=VIDEO_FPS)
        return os.path.relpath(path, self.dir)

    def log_step(self, step: Dict[str, Any]) -> None:
        self.data["steps"].append(step)

    def add_video_frame(self, frame: np.ndarray, status: str = "", repeat: int = 1) -> None:
        if not self.record_video:
            return
        if self.writer is None:
            height, width = frame.shape[:2]
            path = os.path.join(self.dir, "video.mp4")
            # H.264 plays everywhere (browser, QuickTime); not every OpenCV build can write it
            for codec in ("avc1", "mp4v"):
                self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*codec), VIDEO_FPS,
                                              (width, height + 50))
                if self.writer.isOpened():
                    break
        canvas = cv2.copyMakeBorder(frame, 50, 0, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        cv2.putText(canvas, f"Gorev: {self.caption}"[:80], (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, ascii_tr(status)[:80], (10, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 220, 255), 1, cv2.LINE_AA)
        for _ in range(repeat):
            self.writer.write(canvas)

    def finish(self, status: str, message: str, final_frame: Optional[np.ndarray] = None) -> str:
        if final_frame is not None:
            self.add_video_frame(final_frame, f"SONUC: {status} - {message}", repeat=VIDEO_FPS * 2)
        if self.writer is not None:
            self.writer.release()
            self.writer = None

        self.data.update({
            "status": status,
            "message": message,
            "duration_sec": round(time.time() - self.started, 1),
            "num_steps": len(self.data["steps"]),
        })
        with open(os.path.join(self.dir, "episode.json"), "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        return self.dir

    @property
    def steps(self) -> List[Dict[str, Any]]:
        return self.data["steps"]
