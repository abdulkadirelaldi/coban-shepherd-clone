"""
Digital Twin: a simulated top-down camera + robot arm

Lets the full pipeline (Gemini -> calibration -> motion sequence -> verification)
run without any hardware. SimCamera replaces VisionCapture and SimRobot exposes
the same send_move / send_gripper interface as SerialController.

Robot frame (mm): x to the right, y away from the robot base, z up.
The camera sees x in [-160, 160] and y in [60, 300] at 2 px/mm.
"""
import math
import random
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from calibration import Calibration
from vla_engine import Action, Status, StepDecision

IMAGE_SIZE = (640, 480)
PX_PER_MM = 2.0
VIEW_X_MIN, VIEW_Y_MAX = -160.0, 300.0

# Same limits as the firmware
WORKSPACE = {"x": (-250.0, 250.0), "y": (0.0, 300.0), "z": (0.0, 200.0)}
# The gripper can only close around an object when it is this low
CONTACT_Z_MM = 25.0
OPEN_JAW_MM = 44.0

TABLE_COLOR = (196, 203, 208)


@dataclass
class SimObject:
    name: str          # Turkish name, also used by tests and the report
    shape: str         # cube | cylinder | connector | fuse | bin
    color: Tuple[int, int, int]  # BGR
    x: float
    y: float
    w: float           # mm
    h: float           # mm
    label: str = ""    # printed label (bins only, ASCII)
    damaged: bool = False

    @property
    def graspable(self) -> bool:
        return self.shape != "bin"

    def contains(self, x: float, y: float) -> bool:
        return abs(x - self.x) <= self.w / 2 and abs(y - self.y) <= self.h / 2


def mm_to_px(x: float, y: float) -> Tuple[int, int]:
    return int(round((x - VIEW_X_MIN) * PX_PER_MM)), int(round((VIEW_Y_MAX - y) * PX_PER_MM))


def _scene_colors() -> List[SimObject]:
    return [
        SimObject("sarı kutu", "bin", (40, 190, 235), 105, 105, 90, 70, "SARI"),
        SimObject("beyaz tepsi", "bin", (235, 235, 235), -105, 105, 90, 70, "TEPSI"),
        SimObject("kırmızı küp", "cube", (45, 45, 200), -95, 240, 26, 26),
        SimObject("kırmızı küp", "cube", (45, 45, 200), 60, 265, 26, 26),
        SimObject("mavi küp", "cube", (190, 110, 40), -20, 190, 26, 26),
        SimObject("yeşil silindir", "cylinder", (70, 160, 60), 110, 210, 28, 28),
    ]


def _scene_wire_harness() -> List[SimObject]:
    """Wire-harness kitting cell, typical for Bursa / Izmir automotive suppliers."""
    return [
        SimObject("kit tepsisi", "bin", (150, 150, 150), -100, 100, 100, 70, "KIT"),
        SimObject("hurda kutusu", "bin", (60, 90, 170), 110, 100, 80, 70, "HURDA"),
        SimObject("siyah konnektör", "connector", (40, 40, 40), -110, 250, 34, 22),
        SimObject("siyah konnektör", "connector", (40, 40, 40), 20, 270, 34, 22),
        SimObject("beyaz konnektör", "connector", (225, 225, 220), 100, 250, 34, 22),
        SimObject("beyaz konnektör", "connector", (225, 225, 220), -40, 200, 34, 22, damaged=True),
        SimObject("kırmızı sigorta", "fuse", (50, 50, 210), 60, 185, 22, 12),
        SimObject("mavi sigorta", "fuse", (200, 120, 40), 130, 175, 22, 12),
    ]


SCENES: Dict[str, Callable[[], List[SimObject]]] = {
    "renkler": _scene_colors,
    "kablo": _scene_wire_harness,
}


class SimWorld:
    def __init__(self, scene: str = "renkler", park: Tuple[float, float] = (0.0, 30.0),
                 safe_z: float = 80.0):
        if scene not in SCENES:
            raise ValueError(f"Bilinmeyen sahne '{scene}'. Seçenekler: {', '.join(SCENES)}")
        self.objects = SCENES[scene]()
        self.gripper = [park[0], park[1], safe_z]
        self.gripper_open = True
        self.held: Optional[SimObject] = None
        self._table = self._make_table()

    @staticmethod
    def _make_table() -> np.ndarray:
        """Static table texture with a little noise so it does not look synthetic-flat."""
        rng = np.random.default_rng(7)
        table = np.full((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), TABLE_COLOR, dtype=np.int16)
        table += rng.integers(-6, 7, size=(IMAGE_SIZE[1], IMAGE_SIZE[0], 1), dtype=np.int16)
        table = np.clip(table, 0, 255).astype(np.uint8)
        return cv2.GaussianBlur(table, (3, 3), 0)

    def calibration(self) -> Calibration:
        """The simulator knows its exact camera geometry, so calibration is free."""
        robot = [(-160, 300), (160, 300), (160, 60), (-160, 60)]
        pixels = [mm_to_px(x, y) for x, y in robot]
        return Calibration.from_points(pixels, robot, IMAGE_SIZE)

    def container_of(self, obj: SimObject) -> Optional[SimObject]:
        """The bin an object is lying in, if any."""
        if obj is self.held:
            return None
        for b in self.objects:
            if b.shape == "bin" and b.contains(obj.x, obj.y):
                return b
        return None

    def objects_named(self, name: str) -> List[SimObject]:
        return [o for o in self.objects if o.name == name]

    # ---- Rendering ----

    def render(self) -> np.ndarray:
        frame = self._table.copy()
        bins = [o for o in self.objects if o.shape == "bin"]
        items = [o for o in self.objects if o.graspable and o is not self.held]
        for b in bins:
            self._draw_bin(frame, b)
        for o in items:
            self._draw_item(frame, o, o.x, o.y, scale=1.0, shadow=3)
        self._draw_arm(frame)
        return frame

    @staticmethod
    def _rect(x: float, y: float, w: float, h: float, scale: float = 1.0):
        cx, cy = mm_to_px(x, y)
        hw, hh = w * PX_PER_MM * scale / 2, h * PX_PER_MM * scale / 2
        return (int(cx - hw), int(cy - hh)), (int(cx + hw), int(cy + hh))

    def _draw_bin(self, frame, b: SimObject):
        p1, p2 = self._rect(b.x, b.y, b.w, b.h)
        inner = tuple(int(c * 0.85 + 30) for c in b.color)
        cv2.rectangle(frame, p1, p2, inner, -1)
        cv2.rectangle(frame, p1, p2, tuple(int(c * 0.55) for c in b.color), 6)
        if b.label:
            (tw, th), _ = cv2.getTextSize(b.label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cx = (p1[0] + p2[0]) // 2
            cv2.putText(frame, b.label, (cx - tw // 2, p1[1] - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 60), 1, cv2.LINE_AA)

    def _draw_item(self, frame, o: SimObject, x: float, y: float, scale: float, shadow: int):
        dark = tuple(int(c * 0.6) for c in o.color)
        light = tuple(min(255, int(c * 1.15 + 25)) for c in o.color)

        if o.shape == "cylinder":
            cx, cy = mm_to_px(x, y)
            r = int(o.w * PX_PER_MM * scale / 2)
            cv2.circle(frame, (cx + shadow, cy + shadow), r, (150, 155, 160), -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), r, o.color, -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), r, dark, 2, cv2.LINE_AA)
            cv2.circle(frame, (cx - r // 3, cy - r // 3), max(2, r // 4), light, -1, cv2.LINE_AA)
            return

        p1, p2 = self._rect(x, y, o.w, o.h, scale)
        cv2.rectangle(frame, (p1[0] + shadow, p1[1] + shadow), (p2[0] + shadow, p2[1] + shadow),
                      (150, 155, 160), -1)
        cv2.rectangle(frame, p1, p2, o.color, -1)
        cv2.rectangle(frame, p1, p2, dark, 2)

        if o.shape == "cube":
            cv2.line(frame, (p1[0] + 4, p1[1] + 4), (p2[0] - 6, p1[1] + 4), light, 2)
        elif o.shape == "connector":
            pin = (150, 150, 150) if sum(o.color) < 300 else (90, 90, 90)
            cols, rows = 4, 2
            for i in range(cols):
                for j in range(rows):
                    px = int(p1[0] + (i + 0.5) * (p2[0] - p1[0]) / cols)
                    py = int(p1[1] + (j + 0.5) * (p2[1] - p1[1]) / rows)
                    cv2.circle(frame, (px, py), 3, pin, -1, cv2.LINE_AA)
        elif o.shape == "fuse":
            cap = max(3, (p2[0] - p1[0]) // 5)
            cv2.rectangle(frame, p1, (p1[0] + cap, p2[1]), (180, 180, 185), -1)
            cv2.rectangle(frame, (p2[0] - cap, p1[1]), p2, (180, 180, 185), -1)

        if o.damaged:
            # A visible crack across the housing
            pts = np.array([[p1[0] + 3, p1[1] + 5], [p1[0] + 20, p1[1] + 18],
                            [p1[0] + 30, p1[1] + 10], [p2[0] - 12, p2[1] - 4],
                            [p2[0] - 2, p2[1] - 10]], dtype=np.int32)
            cv2.polylines(frame, [pts], False, (20, 20, 20), 3, cv2.LINE_AA)

    def _draw_arm(self, frame):
        gx, gy, gz = self.gripper
        if gy + 15 < VIEW_Y_MAX - IMAGE_SIZE[1] / PX_PER_MM:
            return  # Parked outside the camera view (jaws are 30 mm long)

        # Perspective: the higher the gripper, the bigger it looks from the top camera
        height_scale = 1.0 + gz / 400
        cx, cy = mm_to_px(gx, gy)
        base = mm_to_px(0, -40)
        wrist = (cx, cy + int(30 * height_scale))
        cv2.line(frame, base, wrist, (105, 105, 110), int(22 * height_scale), cv2.LINE_AA)
        cv2.circle(frame, wrist, int(14 * height_scale), (80, 80, 85), -1, cv2.LINE_AA)

        if self.held is not None:
            self._draw_item(frame, self.held, gx, gy, scale=height_scale, shadow=int(4 + gz / 10))

        if self.gripper_open:
            gap = OPEN_JAW_MM
        elif self.held is not None:
            gap = self.held.w + 2
        else:
            gap = 6.0
        for side in (-1, 1):
            jx = gx + side * (gap / 2 + 3.5) * height_scale
            p1, p2 = self._rect(jx, gy, 7, 30, height_scale)
            cv2.rectangle(frame, p1, p2, (70, 70, 75), -1)
            cv2.rectangle(frame, p1, p2, (40, 40, 45), 1)
        # Bar joining the jaws, on the wrist side
        bar1, bar2 = self._rect(gx, gy - 18 * height_scale, gap + 14, 6, height_scale)
        cv2.rectangle(frame, bar1, bar2, (80, 80, 85), -1)


class SimCamera:
    """Drop-in replacement for VisionCapture."""

    def __init__(self, world: SimWorld):
        self.world = world

    def is_opened(self) -> bool:
        return True

    def capture_frame(self) -> np.ndarray:
        return self.world.render()

    def release(self):
        pass


class SimRobot:
    """Drop-in replacement for SerialController, acting on a SimWorld."""

    def __init__(self, world: SimWorld, fail_rate: float = 0.0, seed: Optional[int] = None,
                 on_frame: Optional[Callable[[np.ndarray], None]] = None):
        self.world = world
        self.fail_rate = fail_rate
        self.rng = random.Random(seed)
        self.on_frame = on_frame

    def is_connected(self) -> bool:
        return True

    def _emit(self, repeat: int = 1):
        if self.on_frame:
            frame = self.world.render()
            for _ in range(repeat):
                self.on_frame(frame)

    def send_move(self, x: float, y: float, z: float = 0.0) -> bool:
        for axis, value in zip("xyz", (x, y, z)):
            lo, hi = WORKSPACE[axis]
            if not lo <= value <= hi:
                print(f"[SIM] ERR hedef çalışma alanı dışında ({axis}={value:.1f})")
                return False

        start = list(self.world.gripper)
        dist = math.dist(start, (x, y, z))
        steps = max(3, min(20, int(dist / 15)))
        for i in range(1, steps + 1):
            t = i / steps
            self.world.gripper = [s + (e - s) * t for s, e in zip(start, (x, y, z))]
            self._emit()
        if self.world.held is not None:
            self.world.held.x, self.world.held.y = x, y
        print(f"[SIM] MOVE x={x:.1f} y={y:.1f} z={z:.1f} -> DONE")
        return True

    def send_gripper(self, state: str) -> bool:
        state = state.upper()
        if state not in ("OPEN", "CLOSE"):
            raise ValueError(f"Geçersiz gripper durumu: {state}")
        w = self.world
        gx, gy, gz = w.gripper

        if state == "OPEN":
            if w.held is not None:
                w.held.x, w.held.y = gx, gy
                self._settle(w.held)
                w.held = None
            w.gripper_open = True
        else:
            w.gripper_open = False
            if w.held is None and gz <= CONTACT_Z_MM:
                candidates = [o for o in w.objects if o.graspable
                              and math.hypot(o.x - gx, o.y - gy) <= max(o.w, o.h) / 2 + 6]
                if candidates:
                    target = min(candidates, key=lambda o: math.hypot(o.x - gx, o.y - gy))
                    if self.rng.random() < self.fail_rate:
                        # Slipped: the object gets pushed aside instead of grasped
                        target.x += self.rng.choice((-1, 1)) * self.rng.uniform(12, 20)
                        target.y += self.rng.uniform(-8, 8)
                        print(f"[SIM] '{target.name}' kaydı, tutulamadı.")
                    else:
                        w.held = target
        self._emit(repeat=3)
        print(f"[SIM] GRIPPER {state} -> DONE")
        return True

    def _settle(self, obj: SimObject):
        """A dropped object cannot rest on top of another one: it slides to the nearest free spot."""
        others = [o for o in self.world.objects if o.graspable and o is not obj]
        container = next((b for b in self.world.objects if b.shape == "bin" and b.contains(obj.x, obj.y)), None)

        def free(x, y):
            if container is not None and not (abs(x - container.x) <= (container.w - obj.w) / 2 and
                                              abs(y - container.y) <= (container.h - obj.h) / 2):
                return False  # Stay fully inside the bin it was dropped into
            return all(math.hypot(x - o.x, y - o.y) >= (max(o.w, o.h) + max(obj.w, obj.h)) / 2 + 2
                       for o in others)

        if free(obj.x, obj.y):
            return
        for radius in range(6, 80, 6):
            for k in range(12):
                angle = k * math.pi / 6
                x, y = obj.x + radius * math.cos(angle), obj.y + radius * math.sin(angle)
                if free(x, y):
                    obj.x, obj.y = x, y
                    return

    def close(self):
        pass


# Offline demo tasks: (instruction, object to move, destination bin)
DEMO_TASKS = {
    "renkler": ("kırmızı küpleri sarı kutuya koy", "kırmızı küp", "sarı kutu"),
    "kablo": ("siyah konnektörleri kit tepsisine koy", "siyah konnektör", "kit tepsisi"),
}


class OraclePolicy:
    """
    Stand-in for Gemini that reads the simulator's true state. It solves
    'put every <item> into <bin>' and checks the previous step the way the
    real model is asked to. Used by the tests and by `main.py --offline-demo`
    so the closed loop can be shown without an API key.
    """
    model = "oracle (API'siz demo)"

    def __init__(self, world: SimWorld, item: str, bin_name: str):
        self.world, self.item, self.bin_name = world, item, bin_name

    @staticmethod
    def _decision(status, action, target, x=None, y=None, ok=True, why=""):
        pixel = mm_to_px(x, y) if x is not None else None
        return StepDecision(status, action, target, pixel, 0.95, why, ok)

    def next_step(self, _jpeg, _size, _instruction, history, _holding):
        w = self.world
        bin_obj = w.objects_named(self.bin_name)[0]
        ok = True
        if history:
            if history[-1].startswith("GRAB"):
                ok = w.held is not None
            elif history[-1].startswith("DROP"):
                ok = w.held is None
        if w.held is not None:
            return self._decision(Status.CONTINUE, Action.DROP, self.bin_name, bin_obj.x, bin_obj.y,
                                  ok, f"{w.held.name} {self.bin_name} içine bırakılacak.")
        remaining = [o for o in w.objects_named(self.item) if w.container_of(o) is not bin_obj]
        if not remaining:
            return self._decision(Status.DONE, Action.GRAB, self.item, ok=ok,
                                  why=f"Tüm {self.item} nesneleri {self.bin_name} içinde.")
        o = remaining[0]
        return self._decision(Status.CONTINUE, Action.GRAB, self.item, o.x, o.y,
                              ok, f"Sıradaki {self.item} alınacak.")
