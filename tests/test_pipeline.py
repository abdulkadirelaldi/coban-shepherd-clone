"""
Hardware-free tests for the pipeline. Run with:
    python -m unittest discover tests
"""
import dataclasses
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from calibration import Calibration
from config import load_settings
from episode_logger import ascii_tr, slugify
from privacy import FaceAnonymizer
from serial_controller import SerialController
from simulator import IMAGE_SIZE, OraclePolicy, SimCamera, SimRobot, SimWorld, mm_to_px
from task_runner import RobotExecutor, TaskRunner
from vision_capture import VisionCapture
from vla_engine import (Action, Status, VLAEngine, VLAResponse,
                        build_prompt, normalized_to_pixel)


class FakeSerial:
    """Mimics pyserial: records writes and answers every command with a scripted reply."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.pending = []
        self.written = []
        self.is_open = True

    def reset_input_buffer(self):
        self.pending.clear()

    def write(self, data):
        self.written.append(json.loads(data.decode()))
        self.pending.append(self.replies.pop(0) if self.replies else "")

    def flush(self):
        pass

    def readline(self):
        return (self.pending.pop(0) + "\n").encode() if self.pending else b""

    def close(self):
        self.is_open = False


def make_controller(replies) -> SerialController:
    ctrl = SerialController.__new__(SerialController)
    ctrl.port = "fake"
    ctrl.baudrate = 115200
    ctrl.timeout = 0.01
    ctrl.ack_timeout_sec = 0.2
    ctrl.serial_conn = FakeSerial(replies)
    return ctrl


class FakeModels:
    def __init__(self, text):
        self.text = text
        self.prompts = []

    def generate_content(self, **kwargs):
        self.prompts.append(kwargs["contents"][1])
        return SimpleNamespace(parsed=None, text=self.text)


def make_engine(payload) -> VLAEngine:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return VLAEngine(api_key=None, model="test-model", client=SimpleNamespace(models=FakeModels(text)))


def answer(**overrides):
    base = {"reasoning": "test", "previous_step_succeeded": True, "status": "CONTINUE",
            "action": "GRAB", "target": "kırmızı küp", "point_y": 250, "point_x": 750,
            "confidence": 0.9}
    base.update(overrides)
    return base


def test_settings(tmp: str, **overrides):
    return dataclasses.replace(load_settings(), episodes_dir=os.path.join(tmp, "episodes"),
                               debug_dir=os.path.join(tmp, "debug"), **overrides)


class TestVLAEngine(unittest.TestCase):
    def test_normalized_point_is_scaled_to_real_frame_size(self):
        self.assertEqual(normalized_to_pixel(500, 500, (1280, 720)), (640, 360))
        self.assertEqual(normalized_to_pixel(1000, 1000, (640, 480)), (639, 479))
        self.assertEqual(normalized_to_pixel(0, 0, (640, 480)), (0, 0))

    def test_valid_answer_is_converted(self):
        result = make_engine(answer()).next_step(b"jpeg", (800, 600), "kırmızı küpü al")
        self.assertEqual(result.status, Status.CONTINUE)
        self.assertEqual(result.action, Action.GRAB)
        self.assertEqual(result.pixel, (599, 150))
        self.assertAlmostEqual(result.confidence, 0.9)

    def test_done_has_no_pixel(self):
        result = make_engine(answer(status="DONE", point_x=0, point_y=0)).next_step(b"j", (640, 480), "x")
        self.assertEqual(result.status, Status.DONE)
        self.assertIsNone(result.pixel)

    def test_out_of_range_point_returns_none(self):
        self.assertIsNone(make_engine(answer(point_y=1200)).next_step(b"j", (640, 480), "al"))

    def test_malformed_answer_returns_none(self):
        self.assertIsNone(make_engine("not json").next_step(b"j", (640, 480), "al"))

    def test_prompt_contains_history_and_gripper_state(self):
        engine = make_engine(answer(action="DROP"))
        engine.next_step(b"j", (640, 480), "küpü kutuya koy", ["GRAB kırmızı küp"], "kırmızı küp")
        prompt = engine.client.models.prompts[0]
        self.assertIn("Görev: küpü kutuya koy", prompt)
        self.assertIn("1. GRAB kırmızı küp", prompt)
        self.assertIn("tuttuğu sanılan nesne: kırmızı küp", prompt)
        self.assertIn("Gripper boş", build_prompt("x", [], None))

    def test_schema_keeps_reasoning_first(self):
        self.assertEqual(list(VLAResponse.model_fields)[0], "reasoning")


class TestCalibration(unittest.TestCase):
    # Pixel (u, v) -> robot (x, y): x = 0.5*u - 100, y = 300 - 0.5*v
    PIXELS = [(0, 0), (640, 0), (640, 480), (0, 480), (320, 240)]
    ROBOT = [(-100, 300), (220, 300), (220, 60), (-100, 60), (60, 180)]

    def test_maps_pixels_to_robot_mm(self):
        calib = Calibration.from_points(self.PIXELS, self.ROBOT, (640, 480))
        x, y = calib.pixel_to_robot((160, 120))
        self.assertAlmostEqual(x, -20, places=3)
        self.assertAlmostEqual(y, 240, places=3)
        self.assertLess(calib.mean_error(self.PIXELS, self.ROBOT), 1e-6)

    def test_rescales_different_frame_size(self):
        calib = Calibration.from_points(self.PIXELS, self.ROBOT, (640, 480))
        x, y = calib.pixel_to_robot((320, 240), frame_size=(1280, 960))
        self.assertAlmostEqual(x, -20, places=3)
        self.assertAlmostEqual(y, 240, places=3)

    def test_save_and_load_roundtrip(self):
        calib = Calibration.from_points(self.PIXELS, self.ROBOT, (640, 480))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calibration.json")
            calib.save(path)
            loaded = Calibration.load(path)
        np.testing.assert_allclose(loaded.homography, calib.homography)
        self.assertEqual(loaded.image_size, (640, 480))

    def test_missing_file_returns_none(self):
        self.assertIsNone(Calibration.load("does-not-exist.json"))

    def test_too_few_points_rejected(self):
        with self.assertRaises(ValueError):
            Calibration.from_points(self.PIXELS[:3], self.ROBOT[:3], (640, 480))


class TestSerialController(unittest.TestCase):
    def test_command_waits_for_done(self):
        ctrl = make_controller(["DONE"])
        self.assertTrue(ctrl.send_move(10.04, 20, 30))
        self.assertEqual(ctrl.serial_conn.written[0], {"type": "MOVE", "x": 10.0, "y": 20, "z": 30})

    def test_err_reply_fails(self):
        self.assertFalse(make_controller(["ERR target outside workspace"]).send_gripper("CLOSE"))

    def test_missing_reply_times_out(self):
        self.assertFalse(make_controller([""]).send_gripper("OPEN"))

    def test_invalid_gripper_state_rejected(self):
        with self.assertRaises(ValueError):
            make_controller([]).send_gripper("GRAB")

    def test_no_port_does_not_crash(self):
        ctrl = make_controller([])
        ctrl.serial_conn = None
        ctrl.port = None
        self.assertFalse(ctrl.send_gripper("OPEN"))


class TestRobotExecutor(unittest.TestCase):
    def test_grab_sequence(self):
        ctrl = make_controller(["DONE"] * 5)
        self.assertTrue(RobotExecutor(ctrl, load_settings()).execute(Action.GRAB, 100, 150))
        sent = ctrl.serial_conn.written
        self.assertEqual([c.get("state") or c["type"] for c in sent],
                         ["OPEN", "MOVE", "MOVE", "CLOSE", "MOVE"])
        self.assertGreater(sent[1]["z"], sent[2]["z"])  # Approach from above

    def test_drop_sequence_parks_afterwards(self):
        ctrl = make_controller(["DONE"] * 5)
        settings = load_settings()
        self.assertTrue(RobotExecutor(ctrl, settings).execute(Action.DROP, 100, 150))
        sent = ctrl.serial_conn.written
        self.assertEqual([c.get("state") or c["type"] for c in sent],
                         ["MOVE", "MOVE", "OPEN", "MOVE", "MOVE"])
        self.assertEqual((sent[-1]["x"], sent[-1]["y"]), (settings.park_x_mm, settings.park_y_mm))

    def test_sequence_stops_on_failure(self):
        ctrl = make_controller(["DONE", "ERR move failed", "DONE", "DONE", "DONE"])
        self.assertFalse(RobotExecutor(ctrl, load_settings()).execute(Action.GRAB, 100, 150))
        self.assertEqual(len(ctrl.serial_conn.written), 2)


class TestSimulator(unittest.TestCase):
    def test_calibration_matches_camera_geometry(self):
        world = SimWorld("renkler")
        x, y = world.calibration().pixel_to_robot(mm_to_px(-95, 240))
        self.assertAlmostEqual(x, -95, places=3)
        self.assertAlmostEqual(y, 240, places=3)

    def test_pick_and_place_into_bin(self):
        world = SimWorld("renkler")
        executor = RobotExecutor(SimRobot(world), load_settings())
        cube = world.objects_named("mavi küp")[0]
        bin_obj = world.objects_named("sarı kutu")[0]
        self.assertTrue(executor.execute(Action.GRAB, cube.x, cube.y))
        self.assertIs(world.held, cube)
        self.assertTrue(executor.execute(Action.DROP, bin_obj.x, bin_obj.y))
        self.assertIsNone(world.held)
        self.assertIs(world.container_of(cube), bin_obj)

    def test_grab_on_empty_spot_holds_nothing(self):
        world = SimWorld("renkler")
        RobotExecutor(SimRobot(world), load_settings()).execute(Action.GRAB, 0, 290)
        self.assertIsNone(world.held)

    def test_failed_grasp_pushes_object(self):
        world = SimWorld("renkler")
        cube = world.objects_named("mavi küp")[0]
        before = (cube.x, cube.y)
        RobotExecutor(SimRobot(world, fail_rate=1.0, seed=1), load_settings()).execute(Action.GRAB, *before)
        self.assertIsNone(world.held)
        self.assertNotEqual((cube.x, cube.y), before)

    def test_dropped_objects_do_not_stack(self):
        world = SimWorld("renkler")
        executor = RobotExecutor(SimRobot(world), load_settings())
        bin_obj = world.objects_named("sarı kutu")[0]
        for cube in world.objects_named("kırmızı küp"):
            executor.execute(Action.GRAB, cube.x, cube.y)
            executor.execute(Action.DROP, bin_obj.x, bin_obj.y)
        a, b = world.objects_named("kırmızı küp")
        self.assertGreaterEqual(math.hypot(a.x - b.x, a.y - b.y), a.w)
        self.assertIs(world.container_of(a), bin_obj)
        self.assertIs(world.container_of(b), bin_obj)

    def test_workspace_limits(self):
        self.assertFalse(SimRobot(SimWorld()).send_move(400, 100, 50))

    def test_both_scenes_render(self):
        for scene in ("renkler", "kablo"):
            frame = SimCamera(SimWorld(scene)).capture_frame()
            self.assertEqual(VisionCapture.frame_size(frame), IMAGE_SIZE)
        with self.assertRaises(ValueError):
            SimWorld("yok")


class TestClosedLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_task(self, fail_rate=0.0, seed=None, **settings_overrides):
        settings = test_settings(self.tmp, **settings_overrides)
        world = SimWorld("renkler", park=(settings.park_x_mm, settings.park_y_mm))
        robot = SimRobot(world, fail_rate=fail_rate, seed=seed)
        runner = TaskRunner(OraclePolicy(world, "kırmızı küp", "sarı kutu"), SimCamera(world),
                            RobotExecutor(robot, settings), world.calibration(), settings,
                            "test", record_video=True)
        robot.on_frame = runner.on_robot_frame
        return world, runner.run("kırmızı küpleri sarı kutuya koy")

    def test_task_completes_and_is_logged(self):
        world, result = self.run_task()
        self.assertEqual(result.status, "DONE")
        bin_obj = world.objects_named("sarı kutu")[0]
        for cube in world.objects_named("kırmızı küp"):
            self.assertIs(world.container_of(cube), bin_obj)
        # 2 cubes x (GRAB + DROP) + final DONE check
        self.assertEqual(result.steps, 5)

        with open(os.path.join(result.episode_dir, "episode.json"), encoding="utf-8") as f:
            episode = json.load(f)
        self.assertEqual(episode["status"], "DONE")
        self.assertEqual(len(episode["steps"]), 5)
        self.assertTrue(all("robot_xy_mm" in s for s in episode["steps"][:4]))
        self.assertTrue(os.path.exists(os.path.join(result.episode_dir, "frames", "step_05.jpg")))
        self.assertGreater(os.path.getsize(os.path.join(result.episode_dir, "video.mp4")), 1000)

    def test_recovers_from_failed_grasps(self):
        world, result = self.run_task(fail_rate=0.4, seed=3)
        self.assertEqual(result.status, "DONE")
        self.assertGreater(result.steps, 5)  # Retries were needed
        with open(os.path.join(result.episode_dir, "episode.json"), encoding="utf-8") as f:
            steps = json.load(f)["steps"]
        self.assertIn(False, [s["previous_step_succeeded"] for s in steps])

    def test_gives_up_after_repeated_failures(self):
        _, result = self.run_task(fail_rate=1.0, seed=0, max_retries=2)
        self.assertEqual(result.status, "FAILED")

    def test_low_confidence_does_not_move(self):
        settings = test_settings(self.tmp, min_confidence=0.95)
        world = SimWorld("renkler")
        robot = SimRobot(world)
        runner = TaskRunner(make_engine(answer(confidence=0.5)), SimCamera(world),
                            RobotExecutor(robot, settings), world.calibration(), settings, "test")
        result = runner.run("kırmızı küpü al")
        self.assertEqual(result.status, "FAILED")
        self.assertIsNone(world.held)
        self.assertEqual(world.gripper[:2], [settings.park_x_mm, settings.park_y_mm])

    def test_inconsistent_decision_is_rejected(self):
        settings = test_settings(self.tmp, max_steps=2)
        world = SimWorld("renkler")
        runner = TaskRunner(make_engine(answer(action="DROP")), SimCamera(world),
                            RobotExecutor(SimRobot(world), settings), world.calibration(), settings, "test")
        result = runner.run("bırak")
        self.assertEqual(result.status, "MAX_STEPS")
        self.assertEqual(world.gripper[:2], [settings.park_x_mm, settings.park_y_mm])

    def test_plan_only_without_robot(self):
        settings = test_settings(self.tmp)
        world = SimWorld("renkler")
        runner = TaskRunner(make_engine(answer()), SimCamera(world), None, None, settings, "test")
        self.assertEqual(runner.run("kırmızı küpü al").status, "PLANNED")


class TestHelpers(unittest.TestCase):
    def test_frame_size_and_jpeg(self):
        frame = np.zeros((360, 480, 3), dtype=np.uint8)
        self.assertEqual(VisionCapture.frame_size(frame), (480, 360))
        self.assertTrue(VisionCapture.frame_to_jpeg(frame).startswith(b"\xff\xd8"))

    def test_turkish_text_helpers(self):
        self.assertEqual(ascii_tr("Çatlak şişe ığdır ÖÜ"), "Catlak sise igdir OU")
        self.assertEqual(slugify("Kırmızı küpleri sarı kutuya koy!"), "kirmizi-kupleri-sari-kutuya-koy")

    def test_anonymizer_keeps_frames_without_faces(self):
        frame = SimCamera(SimWorld()).capture_frame()
        out, faces = FaceAnonymizer().anonymize(frame)
        self.assertEqual(faces, 0)
        self.assertIs(out, frame)

    def test_anonymizer_pixelates_detected_faces(self):
        anonymizer = FaceAnonymizer()
        anonymizer._detect = lambda _frame: [(100, 100, 60, 60)]
        frame = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)
        out, faces = anonymizer.anonymize(frame)
        self.assertEqual(faces, 1)
        self.assertFalse(np.array_equal(out[100:160, 100:160], frame[100:160, 100:160]))
        self.assertTrue(np.array_equal(out[:50, :50], frame[:50, :50]))  # Rest untouched


if __name__ == "__main__":
    unittest.main()
