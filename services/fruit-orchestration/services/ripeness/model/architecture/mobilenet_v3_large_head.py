import torch.nn as nn
import torch
from torchvision.models import mobilenet_v3_large, MobileNet_V3_Large_Weights

class RipenessModelConditional(nn.Module):
    """
    Image -> MobileNetV3 backbone
    Fruit type (idx) -> Embedding
    Concatenate -> Linear -> ripeness logits
    """
    def __init__(self, num_ripeness: int, num_fruits: int, embed_dim: int = 16):
        super().__init__()
        weights = MobileNet_V3_Large_Weights.IMAGENET1K_V2
        self.backbone = mobilenet_v3_large(weights=weights)
        in_feats = self.backbone.classifier[-1].in_features
        self.backbone.classifier[-1] = nn.Identity()
        self.fruit_embed = nn.Embedding(num_fruits, embed_dim)
        self.head = nn.Linear(in_feats + embed_dim, num_ripeness)

    def forward(self, x, fruit_idx):
        feats = self.backbone(x)                  # [B, in_feats]
        fvec  = self.fruit_embed(fruit_idx)       # [B, embed_dim]
        out   = torch.cat([feats, fvec], dim=1)   # [B, in_feats+embed_dim]
        return self.head(out)                     # [B, num_ripeness]

def build_conditional(num_ripeness: int, num_fruits: int, embed_dim: int = 16) -> nn.Module:
    return RipenessModelConditional(num_ripeness, num_fruits, embed_dim)

def build_model(num_classes: int) -> nn.Module:
    weights = MobileNet_V3_Large_Weights.IMAGENET1K_V2
    model = mobilenet_v3_large(weights=weights)
    in_feats = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_feats, num_classes)
    return model
