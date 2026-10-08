"""
Serial Controller for Microcontroller (Arduino/STM32) Interface

Protocol (one JSON object per line, 115200 baud):
    PC  -> MCU: {"type": "MOVE", "x": 150.0, "y": -40.0, "z": 80.0}
    PC  -> MCU: {"type": "GRIPPER", "state": "OPEN" | "CLOSE"}
    MCU -> PC : "READY" once after boot
    MCU -> PC : "DONE" when a command has finished, or "ERR <reason>" if it was rejected
"""
import json
import sys
import time
import serial
import serial.tools.list_ports
from typing import Optional

# USB vendor IDs of common Arduino / STM32 / USB-serial boards
KNOWN_VENDOR_IDS = {
    0x2341,  # Arduino
    0x2A03,  # Arduino.org
    0x0483,  # STMicroelectronics (STM32)
    0x1A86,  # CH340 (Arduino clones)
    0x0403,  # FTDI
    0x10C4,  # Silicon Labs CP210x
}


class SerialController:
    def __init__(self, port: Optional[str] = None, baudrate: int = 115200,
                 timeout: float = 1.0, ack_timeout_sec: float = 10.0):
        """
        Initializes the serial connection. If port is None, attempts to auto-detect.
        """
        self.port = port or self.auto_detect_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self.ack_timeout_sec = ack_timeout_sec
        self.serial_conn: Optional[serial.Serial] = None

        if self.port:
            self.connect()
        else:
            print("Uyarı: Seri port belirtilmedi ya da bulunamadı.")

    @staticmethod
    def auto_detect_port() -> Optional[str]:
        """Attempt to automatically find an Arduino/STM32 port."""
        candidates = []
        for p in serial.tools.list_ports.comports():
            if p.vid is None:
                continue  # Not a USB device (e.g. Bluetooth or built-in ports)
            description = f"{p.description} {p.manufacturer or ''}"
            score = 2 if p.vid in KNOWN_VENDOR_IDS else 0
            score += 1 if ("Arduino" in description or "STM" in description) else 0
            # On macOS every device appears twice; /dev/cu.* is the one to open
            if sys.platform == "darwin" and p.device.startswith("/dev/tty."):
                continue
            candidates.append((score, p.device))

        if not candidates:
            return None
        candidates.sort(reverse=True)
        port = candidates[0][1]
        print(f"Port otomatik bulundu: {port}")
        return port

    def connect(self) -> bool:
        """Establish the serial connection and wait for the board to boot."""
        if not self.port:
            return False
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        except serial.SerialException as e:
            print(f"{self.port} portuna bağlanılamadı: {e}")
            self.serial_conn = None
            return False

        # Opening the port resets most Arduinos; wait for the boot message
        if not self._wait_for(("READY",), timeout_sec=3.0):
            print("Not: Karttan READY mesajı gelmedi, devam ediliyor.")
        self.serial_conn.reset_input_buffer()
        print(f"{self.port} portuna {self.baudrate} baud ile bağlanıldı.")
        return True

    def is_connected(self) -> bool:
        """Check if the serial connection is active."""
        return self.serial_conn is not None and self.serial_conn.is_open

    def send_command(self, payload: dict) -> bool:
        """Send a JSON payload and block until the microcontroller reports DONE."""
        if not self.is_connected():
            print("Hata: Seri port bağlı değil. Yeniden bağlanılıyor...")
            if not self.connect():
                return False

        try:
            self.serial_conn.reset_input_buffer()
            json_str = json.dumps(payload) + "\n"
            self.serial_conn.write(json_str.encode('utf-8'))
            self.serial_conn.flush()
            print(f"Gönderildi: {json_str.strip()}")
        except serial.SerialException as e:
            print(f"Seri porta yazılamadı: {e}")
            self.close()
            return False

        return self._wait_for(("DONE",), timeout_sec=self.ack_timeout_sec)

    def send_move(self, x: float, y: float, z: float = 0.0) -> bool:
        """Send a movement command to specific coordinates (mm)."""
        command = {
            "type": "MOVE",
            "x": round(x, 1),
            "y": round(y, 1),
            "z": round(z, 1)
        }
        return self.send_command(command)

    def send_gripper(self, state: str) -> bool:
        """
        Send a gripper command.
        :param state: "OPEN" or "CLOSE"
        """
        state = state.upper()
        if state not in ("OPEN", "CLOSE"):
            raise ValueError(f"Geçersiz gripper durumu: {state}")
        command = {
            "type": "GRIPPER",
            "state": state
        }
        return self.send_command(command)

    def _wait_for(self, expected: tuple, timeout_sec: float) -> bool:
        """Read lines until one of the expected replies, an ERR reply or the timeout."""
        if not self.is_connected():
            return False

        deadline = time.time() + timeout_sec
        try:
            while time.time() < deadline:
                line = self.serial_conn.readline().decode('utf-8', errors='replace').strip()
                if not line:
                    continue
                print(f"Alındı: {line}")
                reply = line.upper()
                if reply.startswith("ERR"):
                    return False
                if any(reply.startswith(e) for e in expected):
                    return True
        except serial.SerialException as e:
            print(f"Seri porttan okunamadı: {e}")
            self.close()
            return False

        print(f"{'/'.join(expected)} beklenirken zaman aşımı.")
        return False

    def close(self):
        """Close the serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("Seri bağlantı kapatıldı.")
        self.serial_conn = None
