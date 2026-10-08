"""
Closed-loop task execution

    observe -> (KVKK blur) -> VLA decides next step + verifies previous one
            -> calibration -> motion sequence -> observe again ...

until the model reports DONE / IMPOSSIBLE, a safety check fails or the
step budget is used up. Every run is logged as an episode (data flywheel).
"""
import os
from dataclasses import dataclass
from typing import Optional
import numpy as np
from calibration import Calibration
from config import Settings
from episode_logger import EpisodeLogger, ascii_tr
from privacy import FaceAnonymizer
from vision_capture import VisionCapture
from vla_engine import Action, Status, VLAEngine

ACTION_TR = {Action.GRAB: "AL", Action.DROP: "BIRAK"}


class RobotExecutor:
    """Turns a GRAB / DROP decision into a safe sequence of robot commands."""

    def __init__(self, robot, settings: Settings):
        # robot: SerialController or SimRobot (same send_move / send_gripper interface)
        self.robot = robot
        self.safe_z = settings.safe_z_mm
        self.grasp_z = settings.grasp_z_mm
        self.park = (settings.park_x_mm, settings.park_y_mm)

    def execute(self, action: Action, x: float, y: float) -> bool:
        """Approach from above, act at table height, then retract. Stops at the first failure."""
        r = self.robot
        if action == Action.GRAB:
            # Stay above the object afterwards so the camera can verify the grasp
            steps = [
                lambda: r.send_gripper("OPEN"),
                lambda: r.send_move(x, y, self.safe_z),
                lambda: r.send_move(x, y, self.grasp_z),
                lambda: r.send_gripper("CLOSE"),
                lambda: r.send_move(x, y, self.safe_z),
            ]
        else:  # Action.DROP
            # Park outside the camera view afterwards so the result is fully visible
            steps = [
                lambda: r.send_move(x, y, self.safe_z),
                lambda: r.send_move(x, y, self.grasp_z),
                lambda: r.send_gripper("OPEN"),
                lambda: r.send_move(x, y, self.safe_z),
                lambda: r.send_move(*self.park, self.safe_z),
            ]

        for i, step in enumerate(steps, start=1):
            if not step():
                print(f"Adım {i}/{len(steps)} başarısız, hareket dizisi durduruldu.")
                return False
        return True


@dataclass
class TaskResult:
    status: str        # DONE | IMPOSSIBLE | FAILED | MAX_STEPS | PLANNED
    message: str
    steps: int
    episode_dir: str


class TaskRunner:
    def __init__(self, engine: VLAEngine, camera, executor: Optional[RobotExecutor],
                 calibration: Optional[Calibration], settings: Settings, mode: str,
                 anonymizer: Optional[FaceAnonymizer] = None, record_video: bool = False):
        """executor=None or calibration=None means plan only: decide the first step, do not move."""
        self.engine = engine
        self.camera = camera
        self.executor = executor
        self.calibration = calibration
        self.settings = settings
        self.mode = mode
        self.anonymizer = anonymizer or FaceAnonymizer(enabled=False)
        self.record_video = record_video
        self.logger: Optional[EpisodeLogger] = None
        self.video_status = ""

    def on_robot_frame(self, frame: np.ndarray) -> None:
        """Called by SimRobot for every animation frame while the arm moves."""
        if self.logger is not None:
            self.logger.add_video_frame(frame, self.video_status)

    def run(self, instruction: str) -> TaskResult:
        s = self.settings
        self.logger = EpisodeLogger(s.episodes_dir, instruction, self.engine.model, self.mode,
                                    record_video=self.record_video)
        history: list = []
        holding: Optional[str] = None
        held_before: Optional[str] = None
        last_action: Optional[Action] = None
        failures = 0
        frame = None

        def finish(status: str, message: str, steps: int) -> TaskResult:
            print(f"\n==> {status}: {message}")
            episode_dir = self.logger.finish(status, message, frame)
            self.logger = None
            print(f"Episode kaydedildi: {episode_dir}")
            return TaskResult(status, message, steps, episode_dir)

        for step in range(1, s.max_steps + 1):
            print(f"\n--- Adım {step}/{s.max_steps} ---")
            frame = self.camera.capture_frame()
            if frame is None:
                return finish("FAILED", "Kameradan görüntü alınamadı.", step)

            frame, faces = self.anonymizer.anonymize(frame)
            if faces:
                print(f"KVKK: {faces} yüz bulanıklaştırıldı.")
            frame_size = VisionCapture.frame_size(frame)
            observation = self.logger.log_observation(step, frame)

            decision = self.engine.next_step(VisionCapture.frame_to_jpeg(frame), frame_size,
                                             instruction, history, holding)
            record = {"step": step, "observation": observation, "faces_blurred": faces,
                      "holding_before": holding}
            if decision is None:
                self.logger.log_step(record)
                return finish("FAILED", "Modelden geçerli bir cevap alınamadı.", step)

            record.update({
                "status": decision.status.value, "action": decision.action.value,
                "target": decision.target, "pixel": decision.pixel,
                "confidence": decision.confidence, "reasoning": decision.reasoning,
                "previous_step_succeeded": decision.previous_step_succeeded,
                "progress": decision.progress,
                "model": getattr(self.engine, "last_model", None) or self.engine.model,
            })

            # 1. Verify the previous step using the new observation
            if last_action is not None:
                if decision.previous_step_succeeded:
                    failures = 0
                    history[-1] += " -> doğrulandı"
                else:
                    failures += 1
                    history[-1] += " -> BAŞARISIZ (görüntüde doğrulanamadı)"
                    holding = None if last_action == Action.GRAB else held_before
                    print(f"Önceki adım başarısız görünüyor ({failures}/{s.max_retries}), yeniden planlanıyor.")
                    if failures >= s.max_retries:
                        self.logger.log_step(record)
                        return finish("FAILED", "Aynı adım üst üste başarısız oldu, operatör kontrolü gerekli.", step)
            last_action = None

            # 2. Task finished or impossible
            if decision.status == Status.DONE:
                self.logger.log_step(record)
                return finish("DONE", decision.reasoning, step)
            if decision.status == Status.IMPOSSIBLE:
                self.logger.log_step(record)
                return finish("IMPOSSIBLE", decision.reasoning, step)

            # 3. Safety and consistency checks
            if decision.confidence < s.min_confidence:
                self.logger.log_step(record)
                return finish("FAILED", f"Güven {decision.confidence:.2f} < {s.min_confidence:.2f}; "
                                        "robot hareket ettirilmedi. Komutu netleştirin.", step)
            if (decision.action == Action.GRAB) == (holding is not None):
                why = "gripper doluyken AL" if holding else "gripper boşken BIRAK"
                print(f"Tutarsız karar reddedildi: {why}.")
                history.append(f"REDDEDİLDİ: {why} istendi")
                record["rejected"] = why
                self.logger.log_step(record)
                continue

            label = f"{ACTION_TR[decision.action]}: {decision.target} ({decision.confidence:.2f})"
            VisionCapture.save_debug_frame(frame, decision.pixel, ascii_tr(label),
                                           os.path.join(s.debug_dir, "last_frame.jpg"))
            print(f"Karar: {label} | {decision.reasoning}")
            if decision.progress:
                print(f"İlerleme: {decision.progress}")

            if self.executor is None or self.calibration is None:
                record["executed"] = False
                self.logger.log_step(record)
                return finish("PLANNED", f"Sadece planlandı (robot yok): {label} @ piksel {decision.pixel}", step)

            # 4. Execute
            x, y = self.calibration.pixel_to_robot(decision.pixel, frame_size)
            record["robot_xy_mm"] = [round(x, 1), round(y, 1)]
            print(f"Hareket: {label} -> robot X:{x:.1f} mm, Y:{y:.1f} mm")
            self.video_status = f"Adim {step}: {label}"
            ok = self.executor.execute(decision.action, x, y)
            record["executed"] = ok
            # Touch feedback: a jaw sensor that closed on nothing is a certain failure
            sensor = getattr(self.executor.robot, "gripper_feedback", None) \
                if decision.action == Action.GRAB else None
            record["gripper_sensor"] = sensor
            self.logger.log_step(record)
            if not ok:
                return finish("FAILED", "Robot komutu başarısız oldu. Robotu kontrol edin.", step)

            if sensor == "EMPTY":
                failures += 1
                history.append(f"GRAB {decision.target} -> BAŞARISIZ (gripper sensörü: çeneler boş kapandı)")
                print(f"Gripper sensörü boş kapandığını bildirdi ({failures}/{s.max_retries}), yeniden planlanıyor.")
                if failures >= s.max_retries:
                    return finish("FAILED", "Aynı adım üst üste başarısız oldu, operatör kontrolü gerekli.", step)
                continue

            sensor_note = " (gripper sensörü: nesne tutuluyor)" if sensor == "HELD" else ""
            history.append(f"{decision.action.value} {decision.target}{sensor_note}")
            held_before = holding
            holding = decision.target if decision.action == Action.GRAB else None
            last_action = decision.action

        frame = self.camera.capture_frame()
        if frame is not None:
            frame, _ = self.anonymizer.anonymize(frame)
        return finish("MAX_STEPS", f"{s.max_steps} adımda tamamlanamadı.", s.max_steps)
