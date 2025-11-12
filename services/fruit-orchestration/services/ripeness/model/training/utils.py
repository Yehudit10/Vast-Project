# import torch, random, numpy as np
# from collections import Counter

# def set_seed(s=42):
#     random.seed(s); np.random.seed(s); torch.manual_seed(s); torch.cuda.manual_seed_all(s)

# def load_class_weights(trainloader, use=True):
#     if not use: return None
#     counts = Counter()
#     for _,y in trainloader:
#         for i in y.numpy(): counts[int(i)]+=1
#     total = sum(counts.values())
#     weights = [total/counts[i] for i in range(len(counts))]
#     return torch.tensor(weights, dtype=torch.float32)
