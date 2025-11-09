import os
from typing import List, Optional, Tuple, Dict
import pandas as pd
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset

class WeedsFromTables(Dataset):
    """
    Supports two modes:
    1) Bounding boxes in tables (image_path + xmin, ymin, xmax, ymax [+ label]) -> builds a mask from boxes.
    2) Without boxes (only Filename/Label) -> loads a corresponding PNG mask file from the masks folder.

    Assumptions:
      - If box_cols=None: a masks directory is required with one mask file per image (same basename, PNG).
      - If class_col exists and is not binary, the mask values should contain matching class indices.
    """

    def __init__(
        self,
        root_dir: str,
        table_files: List[str],
        labels_file: Optional[str] = None,
        image_col: str = "image_path",
        box_cols: Optional[Tuple[str, str, str, str]] = ("xmin", "ymin", "xmax", "ymax"),
        class_col: Optional[str] = "label",
        image_transform=None,
        mask_transform=None,
        masks_dir: str = "masks",   # relative to root_dir
    ):
        self.root_dir = root_dir
        self.image_col = image_col
        self.box_cols = box_cols
        self.class_col = class_col
        self.image_transform = image_transform
        self.mask_transform = mask_transform
        self.masks_dir = os.path.join(root_dir, masks_dir)

        # Load and merge tables
        dfs = []
        for path in table_files:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(path)
            elif ext == ".csv":
                df = pd.read_csv(path)
            else:
                raise ValueError(f"Unsupported table extension: {ext}")
            dfs.append(df)
        if not dfs:
            raise ValueError("No tables loaded.")
        df = pd.concat(dfs, ignore_index=True)
        df.columns = [str(c).strip() for c in df.columns]

        # Flexibility for common column names:
        # If the expected image_col does not exist, try 'Filename'/'filename'
        if self.image_col not in df.columns:
            for cand in ("Filename", "filename", "file_name", "image", "img"):
                if cand in df.columns:
                    self.image_col = cand
                    break
        if self.image_col not in df.columns:
            raise KeyError(f"Missing image column. Expected '{self.image_col}' or a common alternative (e.g., 'Filename').")

        # Drop rows without a valid path/name
        df = df.dropna(subset=[self.image_col]).copy()

        # If there are no boxes → use mask files mode
        self.use_file_masks = self.box_cols is None

        # Optional label mapping
        self.label2id: Optional[Dict[str, int]] = None
        if self.class_col and self.class_col in df.columns:
            if labels_file:
                lex = os.path.splitext(labels_file)[1].lower()
                ldf = pd.read_excel(labels_file) if lex in (".xlsx", ".xls") else pd.read_csv(labels_file)
                cols = {c.lower(): c for c in ldf.columns}
                id_col = cols.get("id") or cols.get("class_id") or list(ldf.columns)[0]
                name_col = cols.get("name") or cols.get("label") or cols.get("class") or list(ldf.columns)[1]
                self.label2id = {str(r[name_col]): int(r[id_col]) for _, r in ldf.iterrows()}
            else:
                uniq = sorted(set(map(str, df[self.class_col].unique())))
                self.label2id = {name: i + 1 for i, name in enumerate(uniq)}  # 0 = background

        # Normalize image path: if the value is only a filename, search for it under root_dir/images/<basename>
        def resolve_path(p: str) -> str:
            p = str(p)
            if os.path.isabs(p):
                return p
            cand = os.path.join(self.root_dir, p)
            if os.path.exists(cand):
                return cand
            return os.path.join(self.root_dir, "images", os.path.basename(p))

        df[self.image_col] = df[self.image_col].map(resolve_path)

        # Save image list and group by image (if boxes exist)
        self.images = list(df[self.image_col].unique())
        self.by_image = None
        if not self.use_file_masks:
            # Ensure bounding box columns exist
            for c in (self.box_cols or ()):
                if c not in df.columns:
                    raise KeyError(f"Missing bbox column '{c}' in tables.")
            self.by_image = {img: subdf for img, subdf in df.groupby(self.image_col, sort=False)}

    def __len__(self):
        return len(self.images)

    @staticmethod
    def _clip_box(x1, y1, x2, y2, W, H):
        x1 = int(np.clip(x1, 0, W))
        y1 = int(np.clip(y1, 0, H))
        x2 = int(np.clip(x2, 0, W))
        y2 = int(np.clip(y2, 0, H))
        if x2 < x1: x1, x2 = x2, x1
        if y2 < y1: y1, y2 = y2, y1
        return x1, y1, x2, y2

    def __getitem__(self, idx):
        img_path = self.images[idx]
        image = Image.open(img_path).convert("RGB")
        W, H = image.size

        if self.use_file_masks:
            # Load mask from a PNG file with the same name as the image
            mask_name = os.path.splitext(os.path.basename(img_path))[0] + ".png"
            mask_path = os.path.join(self.masks_dir, mask_name)
            if not os.path.exists(mask_path):
                raise FileNotFoundError(f"Mask file not found for image: {mask_path}")
            mask = Image.open(mask_path).convert("L")
        else:
            # Build mask from bounding boxes
            mask_np = np.zeros((H, W), dtype=np.uint8)
            rows = self.by_image[self.images[idx]]
            for _, row in rows.iterrows():
                x1, y1, x2, y2 = (row[self.box_cols[0]], row[self.box_cols[1]],
                                  row[self.box_cols[2]], row[self.box_cols[3]])
                x1, y1, x2, y2 = self._clip_box(x1, y1, x2, y2, W, H)
                if self.label2id is not None and self.class_col and self.class_col in row:
                    cls_id = self.label2id.get(str(row[self.class_col]), 1)
                else:
                    cls_id = 1
                mask_np[y1:y2, x1:x2] = cls_id
            mask = Image.fromarray(mask_np, mode="L")

        # Transformations
        if self.image_transform:
            image = self.image_transform(image)
        else:
            image = torch.from_numpy(np.array(image)).permute(2, 0, 1).float() / 255.0

        if self.mask_transform:
            mask = self.mask_transform(mask)
        else:
            mask = torch.from_numpy(np.array(mask, dtype=np.uint8)).long()

        return image, mask
