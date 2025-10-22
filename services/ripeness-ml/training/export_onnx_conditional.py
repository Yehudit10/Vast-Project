import torch, yaml
from models.mobilenet_v3_large_head import build_conditional

if __name__ == "__main__":
    cfg = yaml.safe_load(open("configs/config.yaml"))
    model = build_conditional(num_ripeness=len(cfg["ripeness"]), num_fruits=len(cfg["fruits"]))
    model.load_state_dict(torch.load(cfg["checkpoint_dir"]+"/best_conditional.pt", map_location="cpu"))
    model.eval()

    dummy_img  = torch.randn(1,3,cfg["img_size"],cfg["img_size"])
    dummy_fidx = torch.zeros(1, dtype=torch.long)  # fruit idx
    torch.onnx.export(
        model, (dummy_img, dummy_fidx),
        "ripeness_conditional.onnx",
        input_names=["images","fruit_idx"],
        output_names=["ripeness_logits"],
        opset_version=17,
        dynamic_axes={"images":{0:"batch"}, "fruit_idx":{0:"batch"}, "ripeness_logits":{0:"batch"}}
    )
    print("Exported ripeness_conditional.onnx")
