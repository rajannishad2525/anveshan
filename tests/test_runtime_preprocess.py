"""The startup shortcut must retain the existing evaluation pixels exactly."""
import numpy as np
import pytest
from PIL import Image
from app.semantic_clusters import runtime_preprocess


@pytest.mark.parametrize('size', [(224,224),(256,256),(513,277),(277,513),(65,64)])
def test_runtime_transform_is_exact(size):
    import torch
    from torchvision.transforms import Compose, Resize, CenterCrop, ToTensor, Normalize, InterpolationMode
    reference=Compose([Resize(224,interpolation=InterpolationMode.BICUBIC),CenterCrop(224),ToTensor(),Normalize((0.48145466,0.4578275,0.40821073),(0.26862954,0.26130258,0.27577711))])
    w,h=size
    image=Image.fromarray(np.random.default_rng(7).integers(0,256,(h,w,3),dtype=np.uint8))
    assert torch.equal(reference(image),runtime_preprocess(image))
