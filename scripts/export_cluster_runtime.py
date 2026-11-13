"""Prepare the existing local FP32 model for offline desktop startup (no training)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
args = p.parse_args()
sys.path.insert(0, str(args.root))
import torch
import open_clip
import numpy as np
from app.semantic_clusters import POSITIVE, NEGATIVE, runtime_preprocess
from PIL import Image

torch.set_num_threads(4)
weights = args.root / 'models/RemoteCLIP-ViT-B-32.pt'
model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained=None)
model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
model.eval()
with torch.inference_mode():
    text = model.encode_text(open_clip.get_tokenizer('ViT-B-32')(POSITIVE + NEGATIVE))
    text = (text / text.norm(dim=-1, keepdim=True)).numpy()
compiled = torch.jit.script(model)
# Refuse to ship a changed evaluation transform or changed FP32 outputs.
rng = np.random.default_rng(7)
with torch.inference_mode():
    for w, h in ((224,224),(256,256),(513,277),(277,513),(65,64)):
        image=Image.fromarray(rng.integers(0,256,(h,w,3),dtype=np.uint8))
        original=preprocess(image)
        assert torch.equal(original,runtime_preprocess(image)), 'preprocessing differs'
        assert torch.equal(model.encode_image(original.unsqueeze(0)),compiled.encode_image(original.unsqueeze(0))), 'model output differs'
out = args.root / 'models/remoteclip-runtime.pt'
torch.jit.save(compiled, str(out))
np.save(args.root / 'models/remoteclip-screen.npy', text)
manifest = {
    'weight_size': weights.stat().st_size,
    'weight_mtime_ns': weights.stat().st_mtime_ns,
    'weight_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
    'prompts': POSITIVE + NEGATIVE,
    'torch': torch.__version__,
    'runtime_sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
    'screen_sha256': hashlib.sha256((args.root / 'models/remoteclip-screen.npy').read_bytes()).hexdigest(),
    'runtime_size': out.stat().st_size,
    'runtime_mtime_ns': out.stat().st_mtime_ns,
    'preprocess': str(preprocess),
}
(args.root / 'models/remoteclip-runtime.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest), flush=True)
