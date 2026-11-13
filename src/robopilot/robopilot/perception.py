"""用途：对当前相机图像检查红色标记并保存证据；颜色检测不代表工具箱语义识别。"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class CameraFrame:
    image: np.ndarray
    stamp_ns: int
    frame_id: str
    pose: dict


def image_problem(image):
    if image is None or image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 32:
        return '图像缺失或尺寸/编码无效'
    if image.dtype != np.uint8:
        return '图像必须为 uint8 BGR'
    if np.mean(cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 2]) < 15:
        return '画面过暗，不能可靠判断'
    return None


def detect_red_marker(image):
    problem = image_problem(image)
    if problem:
        return {'status': 'unknown', 'reason': problem}
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 100, 60), (10, 255, 255))
    mask |= cv2.inRange(hsv, (170, 100, 60), (179, 255, 255))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    minimum = max(64, int(image.shape[0] * image.shape[1] * 0.005))
    boxes = [list(map(int, row[:4])) for row in stats[1:count] if row[4] >= minimum]
    return {'status': 'detected' if boxes else 'not_detected', 'boxes': boxes,
            'method': 'opencv_hsv_red_v1',
            'reason': '发现足够大的红色区域' if boxes else '本次视野内未发现足够大的红色区域；不代表整个房间不存在目标'}


def save_evidence(path, frame, result):
    annotated = frame.image.copy()
    for x, y, w, h in result.get('boxes', []):
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), annotated):
        raise OSError('Cannot write image evidence')
