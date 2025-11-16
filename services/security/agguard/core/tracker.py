from .types import Track 

import numpy as np
from dataclasses import dataclass
from boxmot import ByteTrack

@dataclass
class Track:
    track_id: int
    cls: str
    conf: float
    bbox: tuple  # (x1, y1, x2, y2)


class BoxMOTWrapper:
    def __init__(self, method="bytetrack", class_map=None, **kwargs):
        """
        class_map: dict[str,int] — e.g. {"animal":1, "person":2, "vehicle":3}
        """
        self.trk = ByteTrack(**kwargs)
        self.class_map = class_map or {"animal": 1, "person": 2, "vehicle": 3}
        self.inv_class_map = {v: k for k, v in self.class_map.items()}

    def update(self, dets, frame):
        if not dets:
            self.trk.update(np.empty((0,6), dtype=float), frame)
            return []

        # normalize detections (supports both Detection objects and tuples)
        norm_dets = []
        for d in dets:
            if isinstance(d, tuple) and len(d) == 3:
                cls, conf, bbox = d
            else:
                cls, conf, bbox = getattr(d, "cls", None), getattr(d, "conf", None), getattr(d, "bbox", None)
            if bbox is None:
                continue
            norm_dets.append((cls, conf, bbox))

        if not norm_dets:
            return []

        boxes = np.array([b for _, _, b in norm_dets], dtype=float)
        confs = np.array([[float(c or 0.0)] for _, c, _ in norm_dets])
        clss = np.array([[self.class_map.get(c, 0)] for c, _, _ in norm_dets], dtype=float)

        detections = np.concatenate([boxes, confs, clss], axis=1)
        tracks = self.trk.update(detections, frame)

        results = []
        for t in tracks:
            x1, y1, x2, y2, tid, conf, cls_id = map(float, t[:7])
            cls_name = self.inv_class_map.get(int(cls_id), str(int(cls_id)))
            results.append(Track(track_id=int(tid), cls=cls_name, conf=conf, bbox=(x1, y1, x2, y2)))

        return results
