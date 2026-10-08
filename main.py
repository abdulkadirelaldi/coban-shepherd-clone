"""
Çoban — Shepherd Clone, localized for Turkish industry

    python main.py --sim                       # digital twin, only needs a Gemini API key
    python main.py --sim --scene kablo         # wire-harness kitting cell
    python main.py --sim --task "kırmızı küpleri sarı kutuya koy"
    python main.py                             # real camera + robot (needs calibration.json)
    python main.py --dry-run                   # real camera, plan only, robot never moves
    python main.py --sim --offline-demo        # no API key: scripted policy shows the closed loop
"""
import argparse
import sys
from typing import Optional
from calibration import Calibration
from config import load_settings
from privacy import FaceAnonymizer
from serial_controller import SerialController
from task_runner import RobotExecutor, TaskRunner
from vision_capture import VisionCapture
from vla_engine import VLAEngine

EXAMPLES = {
    "renkler": ["kırmızı küpleri sarı kutuya koy",
                "mavi küpü beyaz tepsiye bırak",
                "masadaki her şeyi renklerine göre kutulara ayır"],
    "kablo": ["iki siyah konnektörü ve kırmızı sigortayı kit tepsisine koy",
              "çatlak olan konnektörü hurda kutusuna at",
              "kit tepsisine birer tane sağlam beyaz ve siyah konnektör koy"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Çoban: Türkçe komutla çalışan VLA robot kol")
    parser.add_argument("--sim", action="store_true", help="Donanım yerine dijital ikiz (simülasyon) kullan")
    parser.add_argument("--scene", default="renkler", help="Simülasyon sahnesi: renkler | kablo")
    parser.add_argument("--fail-rate", type=float, default=0.0,
                        help="Simülasyonda tutma hatası olasılığı (0-1), kapalı döngü demosu için")
    parser.add_argument("--seed", type=int, help="Simülasyon rastgelelik tohumu")
    parser.add_argument("--no-gripper-sensor", action="store_true",
                        help="Simülasyonda gripper sensörünü kapat (doğrulama sadece görüntüden)")
    parser.add_argument("--task", help="Tek bir görevi çalıştırıp çık")
    parser.add_argument("--offline-demo", action="store_true",
                        help="API anahtarı olmadan, kâhin politika ile hazır demo görevini çalıştır (--sim ile)")
    parser.add_argument("--dry-run", action="store_true", help="Robotu hareket ettirme, sadece planla")
    parser.add_argument("--port", help="Seri port (varsayılan: SERIAL_PORT ya da otomatik)")
    parser.add_argument("--camera", type=int, help="Kamera numarası (varsayılan: CAMERA_INDEX)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()

    print("=======================================")
    print(" Çoban — Shepherd Clone (TR) ")
    print("=======================================")

    if args.offline_demo and not args.sim:
        print("Hata: --offline-demo sadece --sim ile kullanılabilir.")
        return 1

    # 1. VLA engine first: no point opening hardware without an API key
    engine = None
    if not args.offline_demo:
        print(f"\nVLA motoru başlatılıyor (Gemini: {settings.gemini_model})...")
        try:
            engine = VLAEngine(settings.gemini_api_key, settings.gemini_model,
                               fallback_model=settings.gemini_fallback_model)
        except ValueError as e:
            print(f"Ayar hatası: {e}")
            print(".env.example dosyasını .env olarak kopyalayıp GEMINI_API_KEY değerini girin.")
            print("API anahtarı olmadan denemek için: python main.py --sim --offline-demo")
            return 1

    anonymizer = FaceAnonymizer(enabled=settings.blur_faces)
    serial_ctrl: Optional[SerialController] = None

    # 2. Camera, robot and calibration: simulated or real
    if args.sim:
        from simulator import DEMO_TASKS, OraclePolicy, SimCamera, SimRobot, SimWorld
        try:
            world = SimWorld(args.scene, park=(settings.park_x_mm, settings.park_y_mm),
                             safe_z=settings.safe_z_mm)
        except ValueError as e:
            print(f"Hata: {e}")
            return 1
        camera = SimCamera(world)
        robot = SimRobot(world, fail_rate=args.fail_rate, seed=args.seed,
                         gripper_sensor=not args.no_gripper_sensor)
        calibration = world.calibration()
        executor: Optional[RobotExecutor] = RobotExecutor(robot, settings)
        mode = f"SİMÜLASYON ({args.scene})"
        if args.offline_demo:
            instruction, item, bin_name = DEMO_TASKS[args.scene]
            engine = OraclePolicy(world, item, bin_name)
            args.task = instruction
            mode += " + KÂHİN POLİTİKA (Gemini kullanılmıyor)"
    else:
        calibration = Calibration.load(settings.calibration_file)
        if calibration is None:
            print(f"\nUyarı: {settings.calibration_file} bulunamadı. Önce 'python calibration.py' çalıştırın.")
            print("Kalibrasyon olmadan piksel robot koordinatına çevrilemez; robot hareket ETTİRİLMEYECEK.")

        robot = None
        if args.dry_run:
            print("\nKuru çalıştırma: seri bağlantı kapalı.")
        elif calibration is not None:
            print("\nSeri bağlantı başlatılıyor...")
            serial_ctrl = SerialController(args.port or settings.serial_port, settings.serial_baudrate,
                                           ack_timeout_sec=settings.ack_timeout_sec)
            if serial_ctrl.is_connected():
                robot = serial_ctrl
            else:
                print("Not: Robot bağlı değil; sadece planlama yapılacak.")
                serial_ctrl = None
        executor = RobotExecutor(robot, settings) if robot else None

        camera_index = args.camera if args.camera is not None else settings.camera_index
        print(f"\nKamera {camera_index} açılıyor...")
        camera = VisionCapture(camera_index, (settings.camera_width, settings.camera_height))
        if not camera.is_opened():
            print("Hata: Kamera gerekli. CAMERA_INDEX değerini ve kamera iznini kontrol edin.")
            if serial_ctrl:
                serial_ctrl.close()
            return 1
        mode = "DONANIM" if executor else "SADECE PLANLAMA"

    runner = TaskRunner(engine, camera, executor, calibration, settings, mode,
                        anonymizer=anonymizer, record_video=args.sim)
    if args.sim:
        robot.on_frame = runner.on_robot_frame

    print(f"\nSistem hazır. Mod: {mode} | min güven {settings.min_confidence:.2f} | "
          f"en fazla {settings.max_steps} adım | KVKK yüz bulanıklaştırma: "
          f"{'açık' if anonymizer.enabled else 'kapalı'}")
    if args.sim:
        print("Örnek komutlar:")
        for example in EXAMPLES.get(args.scene, []):
            print(f"  - {example}")

    try:
        if args.task:
            result = runner.run(args.task)
            return 0 if result.status in ("DONE", "PLANNED") else 2

        while True:
            print("\n---------------------------------------")
            instruction = input("Robot için komut girin ('q' = çıkış): ").strip()
            if instruction.lower() in ['q', 'quit', 'exit', 'çık', 'cik']:
                break
            if instruction:
                runner.run(instruction)

    except (KeyboardInterrupt, EOFError):
        print("\nKullanıcı kapattı.")
    finally:
        camera.release()
        if serial_ctrl:
            serial_ctrl.close()
        print("Sistem kapatıldı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
