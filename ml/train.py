"""Fine-tune MobileNetV3-Small on thermal person vs background crops.

  py ml/train.py --crops ml/data/crops --epochs 5

With --history, every epoch's train loss / accuracy and holdout loss / accuracy go to a JSON
file (the AI Lab training curve). It refuses to overwrite an existing model unless --overwrite,
so a logged retrain can never replace the shipped ml/models/detector.pt by accident.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset
from torchvision.datasets import ImageFolder

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

ML_DIR = Path(__file__).resolve().parent


def evaluate(model, loader, device, loss_fn=None):
    """Holdout accuracy at the deployed threshold, and mean loss if loss_fn is given."""
    model.eval()
    correct = total = 0
    loss_sum = 0.0
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x).float()
            p = torch.softmax(logits, dim=1)[:, 1]
            correct += ((p >= common.THRESHOLD).long() == y).sum().item()
            total += y.numel()
            if loss_fn is not None:
                loss_sum += loss_fn(logits, y).item() * y.numel()
    acc = correct / max(total, 1)
    return (acc, loss_sum / max(total, 1)) if loss_fn is not None else acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", default=str(ML_DIR / "data" / "crops"))
    ap.add_argument("--out", default=str(ML_DIR / "models" / "detector.pt"))
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-pretrained", action="store_true")
    ap.add_argument("--history", default=None, help="write per-epoch curve JSON here")
    ap.add_argument("--overwrite", action="store_true", help="allow replacing an existing --out")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.overwrite:
        sys.exit(f"{args.out} exists; pass a new --out (or --overwrite on purpose)")

    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}" + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else ""))

    root = Path(args.crops) / "train"
    train_full = ImageFolder(root, transform=common.train_transform())
    hold_full = ImageFolder(root, transform=common.eval_transform())
    assert train_full.classes == common.CLASSES, f"expected {common.CLASSES}, got {train_full.classes}"
    g = torch.Generator().manual_seed(args.seed)
    perm = torch.randperm(len(train_full), generator=g).tolist()
    n_hold = max(1, len(perm) // 10)
    hold_idx, train_idx = perm[:n_hold], perm[n_hold:]
    train_ds, hold_ds = Subset(train_full, train_idx), Subset(hold_full, hold_idx)
    print(f"train {len(train_ds)}, holdout {len(hold_ds)}")

    pin = device == "cuda"
    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=args.workers,
                          pin_memory=pin, persistent_workers=args.workers > 0)
    hold_dl = DataLoader(hold_ds, batch_size=256, num_workers=args.workers, pin_memory=pin)

    model = common.build_model(pretrained=not args.no_pretrained).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    steps = args.epochs * max(1, len(train_dl))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=0.15)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")
    loss_fn = nn.CrossEntropyLoss()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    best = -1.0
    history = []
    for ep in range(1, args.epochs + 1):
        model.train()
        t0, run_loss, n, run_correct = time.time(), 0.0, 0, 0
        for x, y in train_dl:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                logits = model(x)
                loss = loss_fn(logits, y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            run_loss += loss.item() * y.numel()
            n += y.numel()
            p = torch.softmax(logits.detach().float(), dim=1)[:, 1]
            run_correct += ((p >= common.THRESHOLD).long() == y).sum().item()
        acc, val_loss = evaluate(model, hold_dl, device, loss_fn)
        secs = time.time() - t0
        print(f"epoch {ep}/{args.epochs}  loss {run_loss / max(n, 1):.4f}  holdout acc {acc:.4f}  {secs:.1f}s")
        history.append({"epoch": ep, "train_loss": round(run_loss / max(n, 1), 4),
                        "train_acc": round(run_correct / max(n, 1), 4),
                        "val_loss": round(val_loss, 4), "val_acc": round(acc, 4), "seconds": round(secs, 1)})
        if args.history:
            Path(args.history).parent.mkdir(parents=True, exist_ok=True)
            Path(args.history).write_text(json.dumps({
                "arch": common.ARCH, "epochs": args.epochs, "batch": args.batch, "lr": args.lr,
                "seed": args.seed, "device": device, "train": len(train_ds), "holdout": len(hold_ds),
                "note": "holdout = 10% of the FLIR train crops (val_*); the test metrics use FLIR val",
                "curve": history}, indent=1))
        if acc >= best:   # ties: keep the later, better-trained epoch
            best = acc
            common.save_checkpoint(model.cpu(), out, {"holdout_acc": acc, "epoch": ep})
            model.to(device)
    print(f"best holdout acc {best:.4f} -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
