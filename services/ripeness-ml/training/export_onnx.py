import torch, yaml
from models.mobilenet_v3_large_head import build_model

if __name__ == "__main__":
    cfg = yaml.safe_load(open("configs/config.yaml"))
    model = build_model(num_classes=len(cfg["classes"]))
    model.load_state_dict(torch.load(cfg["checkpoint_dir"]+"/best.pt", map_location="cpu"))
    model.eval()
    dummy = torch.randn(1,3,cfg["img_size"],cfg["img_size"])
    torch.onnx.export(model, dummy, "ripeness_mobilenet_v3.onnx",
                      input_names=["images"], output_names=["logits"],
                      opset_version=17, dynamic_axes={"images":{0:"batch"}, "logits":{0:"batch"}})
    print("Exported: ripeness_mobilenet_v3.onnx")
