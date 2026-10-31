"""用途：定义导航后端接口及结果，并提供可注入故障的 mock 后端验证执行逻辑。"""

from dataclasses import dataclass, field
from typing import Protocol

from .schemas import Pose


@dataclass
class NavigationResult:
    status: str
    code: str = ''
    message: str = ''
    safe_to_continue: bool = True
    feedback: dict = field(default_factory=dict)


class NavigationBackend(Protocol):
    name: str

    def prepare(self, timeout_s: float) -> Pose: ...
    def navigate(self, pose: Pose, timeout_s: float) -> NavigationResult: ...
    def cancel(self) -> bool: ...
    def close(self) -> None: ...


class MockBackend:
    """Each configured outcome is consumed by one attempt, not by one step."""

    name = 'mock'

    def __init__(self, outcomes=(), start=None, images=()):
        self.outcomes = list(outcomes)
        self.start = start or Pose(0.0, 0.0, 0.0)
        self.visited = []
        self.cancel_called = False
        self.images = list(images)
        self.position = self.start

    def prepare(self, timeout_s):
        return self.start

    def navigate(self, pose, timeout_s):
        self.visited.append(pose)
        outcome = self.outcomes.pop(0) if self.outcomes else 'succeeded'
        if outcome == 'interrupt':
            raise KeyboardInterrupt
        mapping = {
            'succeeded': NavigationResult('SUCCEEDED'),
            'failed': NavigationResult('FAILED', 'MOCK_UNREACHABLE', 'Injected mock failure'),
            'timeout': NavigationResult('TIMED_OUT', 'MOCK_TIMEOUT', 'Injected mock timeout'),
            'unsafe': NavigationResult('FAILED', 'MOCK_CANCEL_UNCONFIRMED',
                                       'Injected unconfirmed cancellation', False),
        }
        result = mapping[outcome]
        if result.status == 'SUCCEEDED':
            self.position = pose
        return result

    def capture_image(self, timeout_s):
        import time
        import numpy as np
        from dataclasses import asdict
        from .perception import CameraFrame
        outcome = self.images.pop(0) if self.images else 'red'
        if outcome == 'missing':
            raise TimeoutError('Injected missing mock image')
        image = np.full((240, 320, 3), 100 if outcome != 'dark' else 0, dtype=np.uint8)
        if outcome == 'red':
            image[70:170, 100:220] = (0, 0, 220)
        return CameraFrame(image, time.time_ns(), 'mock_camera', asdict(self.position))

    def cancel(self):
        self.cancel_called = True
        return True

    def close(self):
        pass
