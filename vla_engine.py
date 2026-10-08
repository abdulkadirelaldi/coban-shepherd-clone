"""
VLA Prompt Engineering & API Integration (The Core)

Closed-loop policy: on every call the model sees a fresh image, the task,
the step history and the believed gripper state, verifies the previous step
and decides only the NEXT step. This mimics how VLA policies re-plan from
new observations instead of executing a fixed open-loop plan.
"""
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import errors, types

# Gemini returns points normalized to a 0-1000 grid, independent of image size
NORMALIZED_MAX = 1000

# Overloaded / rate limited / server errors are temporary: retry with backoff
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS_SEC = (3, 8, 15, 30)

SYSTEM_INSTRUCTION = """\
You are "Çoban", the closed-loop brain of a pick-and-place robot arm working in a Turkish factory.
On every call you receive a fresh top-down image of the workspace, the operator's task (usually in
Turkish), the steps executed so far and what the gripper is believed to hold. Decide ONLY the next step.

Rules:
1. First look at the image and check whether the previous step really succeeded:
   - after GRAB the object must be between the gripper jaws and gone from its old place,
   - after DROP the object must lie at the drop location and the gripper must be empty.
   Set previous_step_succeeded accordingly (true if there was no previous step).
2. Keep count. In progress, write in Turkish how many of each requested object are already at their
   destination versus how many the task asks for, e.g. "kit tepsisi: 2/2 siyah konnektör, 0/1 kırmızı sigorta".
   Never move more objects than requested. Check colors and damage carefully: a white connector is not
   a black one, a cracked part is not an intact one.
   Before answering DONE, verify that every requested object is at its destination and that you did not
   put any object there that the task did not ask for.
3. If the task is completely done, status=DONE. If it cannot be done (object missing, task
   ambiguous or unsafe), status=IMPOSSIBLE. Otherwise status=CONTINUE with exactly one action:
   - GRAB: only when the gripper is empty. Point at the center of the object to pick up.
   - DROP: only when the gripper holds an object. Point at where it must be put down
     (inside the requested container or on a free spot of the table, never on another object).
4. Handle one object at a time. Never pick an object that is already where the task wants it.
5. point_y and point_x are normalized to 0-1000 (0,0 = top-left, 1000,1000 = bottom-right).
   Use 0,0 when status is DONE or IMPOSSIBLE.
6. target: short Turkish name of the object or place, e.g. "kırmızı küp", "sarı kutu".
7. reasoning: one short sentence in Turkish.
8. confidence: your probability (0.0-1.0) that this step and point are correct.
"""


VERIFY_INSTRUCTION = """\
You are the quality inspector of a pick-and-place robot cell. You receive a top-down image of the
workspace and the operator's task (usually in Turkish). The robot claims the task is finished.
Do not trust that claim: check the image yourself.
For every kind of object the task mentions, count how many are at their destination and how many are
still somewhere else. A requested object still lying on the table means the task is NOT complete.
Also check that no object the task did not ask for was put into the destination.
complete: true only if the image shows the task fully done.
missing: short Turkish description of what is still wrong (empty if complete).
reasoning: one short Turkish sentence with your counts.
"""


class Action(str, Enum):
    GRAB = "GRAB"
    DROP = "DROP"


class Status(str, Enum):
    CONTINUE = "CONTINUE"
    DONE = "DONE"
    IMPOSSIBLE = "IMPOSSIBLE"


class VLAResponse(BaseModel):
    """JSON schema the model is forced to answer with."""
    reasoning: str
    previous_step_succeeded: bool
    progress: str
    status: Status
    action: Action
    target: str
    point_y: int
    point_x: int
    confidence: float


class VerifyResponse(BaseModel):
    """Answer of the independent end-of-task check."""
    reasoning: str
    missing: str
    complete: bool


@dataclass
class StepDecision:
    """Validated model output, with the point converted to pixels of the analysed frame."""
    status: Status
    action: Action
    target: str
    pixel: Optional[Tuple[int, int]]
    confidence: float
    reasoning: str
    previous_step_succeeded: bool
    progress: str = ""


def normalized_to_pixel(point_x: int, point_y: int, image_size: Tuple[int, int]) -> Tuple[int, int]:
    """Convert a 0-1000 normalized point to pixel coordinates for an image of (width, height)."""
    width, height = image_size
    px = round(point_x / NORMALIZED_MAX * (width - 1))
    py = round(point_y / NORMALIZED_MAX * (height - 1))
    return px, py


def build_prompt(instruction: str, history: List[str], holding: Optional[str]) -> str:
    """Describe the task state in Turkish, the operator's language."""
    lines = [f"Görev: {instruction}"]
    if history:
        lines.append("Şu ana kadar yapılan adımlar:")
        lines += [f"{i}. {h}" for i, h in enumerate(history, start=1)]
    else:
        lines.append("Henüz hiçbir adım yapılmadı.")
    lines.append(f"Gripper'ın tuttuğu sanılan nesne: {holding}" if holding
                 else "Gripper boş olmalı.")
    return "\n".join(lines)


class VLAEngine:
    def __init__(self, api_key: Optional[str], model: str, client: Optional[genai.Client] = None,
                 fallback_model: Optional[str] = None, retry_delays: Tuple[float, ...] = RETRY_DELAYS_SEC):
        """Initialize the Gemini client. A client can be injected for testing."""
        if client is None:
            if not api_key:
                raise ValueError("GEMINI_API_KEY tanımlı değil. .env dosyasını oluşturun.")
            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60_000))

        self.client = client
        self.model = model
        self.fallback_model = fallback_model if fallback_model != model else None
        # The model that produced the last answer (the fallback may have been used)
        self.last_model: Optional[str] = None
        self.retry_delays = retry_delays
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=VLAResponse,
            # No tools are used, so disable automatic function calling
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self.verify_config = types.GenerateContentConfig(
            system_instruction=VERIFY_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=VerifyResponse,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def next_step(self, jpeg_bytes: bytes, image_size: Tuple[int, int], instruction: str,
                  history: Optional[List[str]] = None,
                  holding: Optional[str] = None) -> Optional[StepDecision]:
        """
        Ask the model for the next step. Returns None if the call fails
        or the answer is malformed.
        """
        prompt = build_prompt(instruction, history or [], holding)
        contents = [types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"), prompt]
        response = self._generate(contents)
        if response is None:
            return None

        result = self._parse(response, VLAResponse)
        if result is None:
            return None

        print(f"VLA cevabı: {json.dumps(result.model_dump(mode='json'), indent=2, ensure_ascii=False)}")

        pixel = None
        if result.status == Status.CONTINUE:
            if not (0 <= result.point_x <= NORMALIZED_MAX and 0 <= result.point_y <= NORMALIZED_MAX):
                print(f"VLA hatası: ({result.point_x}, {result.point_y}) noktası 0-1000 aralığının dışında.")
                return None
            pixel = normalized_to_pixel(result.point_x, result.point_y, image_size)

        return StepDecision(
            status=result.status,
            action=result.action,
            target=result.target,
            pixel=pixel,
            confidence=max(0.0, min(1.0, result.confidence)),
            reasoning=result.reasoning,
            previous_step_succeeded=result.previous_step_succeeded,
            progress=result.progress,
        )

    def verify_done(self, jpeg_bytes: bytes, instruction: str) -> Optional[VerifyResponse]:
        """
        Independent second look before accepting DONE: the step policy can be wrong about
        its own progress, so a separate inspector prompt checks the final image.
        """
        print("Bitiş doğrulaması yapılıyor...")
        contents = [types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                    f"Görev: {instruction}\nRobot görevin tamamlandığını söylüyor. Görüntüyü kontrol et."]
        response = self._generate(contents, self.verify_config)
        if response is None:
            return None
        result = self._parse(response, VerifyResponse)
        if result is not None:
            print(f"Bitiş doğrulaması: {'TAMAM' if result.complete else 'EKSİK'} | {result.reasoning}")
        return result

    def _generate(self, contents, config=None):
        """Call the model, retrying temporary errors, then falling back to a second model."""
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])
        for model in models:
            for attempt in range(len(self.retry_delays) + 1):
                print(f"VLA modeline soruluyor ({model})...")
                try:
                    response = self.client.models.generate_content(model=model, contents=contents,
                                                                   config=config or self.config)
                    self.last_model = model
                    return response
                except errors.APIError as e:
                    if e.code not in RETRYABLE_STATUS:
                        print(f"VLA API hatası: {e}")
                        return None
                    if attempt < len(self.retry_delays):
                        delay = self.retry_delays[attempt]
                        print(f"Model geçici olarak yanıt veremiyor ({e.code}), {delay} sn sonra tekrar denenecek...")
                        time.sleep(delay)
                except Exception as e:
                    print(f"VLA API hatası: {e}")
                    return None
            if model != models[-1]:
                print(f"{model} yanıt vermiyor, yedek modele geçiliyor.")
        print("VLA API hatası: model şu an yanıt vermiyor, daha sonra tekrar deneyin.")
        return None

    @staticmethod
    def _parse(response, schema):
        """Read the structured answer, falling back to parsing the raw text."""
        if isinstance(getattr(response, "parsed", None), schema):
            return response.parsed

        text = getattr(response, "text", None)
        if not text:
            print("Hata: VLA modelinden boş cevap geldi (güvenlik filtresi olabilir).")
            return None
        try:
            return schema.model_validate_json(text)
        except ValidationError as e:
            print(f"VLA cevabı çözümlenemedi: {e}")
            print(f"Ham cevap: {text}")
            return None
