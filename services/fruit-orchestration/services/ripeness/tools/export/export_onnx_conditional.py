import torch, yaml, os
from model.architecture.mobilenet_v3_large_head import build_conditional

if __name__ == "__main__":
    cfg = yaml.safe_load(open("configs/config.yaml"))
    fruits = cfg["fruits"]
    ripeness = cfg["ripeness"]

    model = build_conditional(num_ripeness=len(ripeness), num_fruits=len(fruits))
    ckpt_path = os.path.join(cfg["checkpoint_dir"], "best_conditional.pt")
    model.load_state_dict(torch.load(ckpt_path, map_location="cpu"))
    model.eval()

    dummy_x = torch.randn(1, 3, cfg["img_size"], cfg["img_size"])
    dummy_f = torch.zeros(1, dtype=torch.long)  # example fruit index
    torch.onnx.export(
        model, (dummy_x, dummy_f),
        "ripeness_conditional.onnx",
        input_names=["image", "fruit_idx"],
        output_names=["ripeness_logits"],
        dynamic_axes={"image": {0: "batch"}, "ripeness_logits": {0: "batch"}},
        opset_version=13
    )

    print("✅ Exported: ripeness_conditional.onnx")
