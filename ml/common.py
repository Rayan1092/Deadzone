"""Shared model + preprocessing for train, eval and the robot perception hook.

Keep this file free of heavy imports at module level beyond torch/torchvision,
so perception.py can import it lazily and fall back if torch is missing.
"""
import torch
from torch import nn

IMG_SIZE = 96
MEAN = [0.485, 0.456, 0.406]   # ImageNet, thermal gray repeated to 3 channels
STD = [0.229, 0.224, 0.225]
THRESHOLD = 0.6
ARCH = "mobilenet_v3_small"
CLASSES = ["neg", "pos"]       # index 1 = person / survivor


def build_model(pretrained=True):
    from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
    m = mobilenet_v3_small(weights=weights)
    m.classifier[3] = nn.Linear(m.classifier[3].in_features, 2)
    return m


def eval_transform():
    from torchvision import transforms as T
    return T.Compose([
        T.Grayscale(num_output_channels=3),
        T.Resize((IMG_SIZE, IMG_SIZE)),
        T.ToTensor(),
        T.Normalize(MEAN, STD),
    ])


def train_transform():
    from torchvision import transforms as T
    return T.Compose([
        T.Grayscale(num_output_channels=3),
        T.RandomResizedCrop(IMG_SIZE, scale=(0.8, 1.0), ratio=(0.9, 1.1)),
        T.RandomHorizontalFlip(),
        T.ColorJitter(brightness=0.25, contrast=0.25),
        T.ToTensor(),
        T.Normalize(MEAN, STD),
    ])


def save_checkpoint(model, path, extra=None):
    ckpt = {"state_dict": model.state_dict(), "arch": ARCH, "img_size": IMG_SIZE,
            "mean": MEAN, "std": STD, "threshold": THRESHOLD, "classes": CLASSES}
    ckpt.update(extra or {})
    torch.save(ckpt, path)


def load_checkpoint(path, device="cpu"):
    ckpt = torch.load(path, map_location=device, weights_only=False)
    model = build_model(pretrained=False)
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    return model, ckpt


@torch.no_grad()
def predict_pos_prob(model, batch):
    """batch: N x 3 x H x W tensor already on the model's device. Returns P(person)."""
    return torch.softmax(model(batch).float(), dim=1)[:, 1]
