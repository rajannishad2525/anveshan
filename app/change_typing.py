"""Zero-shot change typing for screened candidates. Explainable, never trained here.

PS 2.2.2 asks for supported change types (construction, clearance, water-extent
variation, road development) and for the form of the change (appearance,
disappearance, expansion, contraction). This module supplies both from the
RemoteCLIP checkpoint already staged for retrieval. Nothing is trained, no
labels are needed, and no new weights are introduced.

How it works, in one paragraph: a candidate region is cropped from the
registered before image and from the normalized after image. Both crops are
scored against five land-cover prompt groups. The *difference* between the two
probability vectors says which cover rose and which fell, and a small table of
rules turns that into a change type. The form is decided by asking whether the
cover that rose is already present immediately around the region -- if it is,
the feature grew into the region (expansion); if it is not, it appeared.

What this is not:

* Not object detection. A type is a statement about land cover, not about
  identified objects, vehicles or installations.
* Not validated. These labels have not been measured against an independent
  labelled set, so every result carries ``validated: False`` and the caller
  must keep presenting regions as candidates.
* Not spectral. Spectral typing (NDVI/NDWI) needs a real near-infrared band.
  The archive's GeoTIFFs carry an alpha channel as band 4, not NIR, so that
  path is deliberately absent rather than faked.

Measured limitation, recorded rather than hidden: on a 7-image hand-checked
probe (``reality_check/probe_change_typing.py``) the land-cover head scores
6/7, and its one failure over-predicts water on a mixed urban-and-bare tile.
Absolute land-cover probabilities on cluttered urban scenes at this resolution
should therefore be treated as weak. Change *typing* is less exposed to that
bias than single-image classification, because a bias present in both the
before and the after crop largely cancels in the difference -- but "less
exposed" is not "immune", which is why every result carries its own class
probabilities so an analyst can see the basis for the label.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# Five land-cover groups. Several prompts per group, averaged, so the result
# does not hang on the wording of any single sentence.
#
# The wording is not arbitrary. A first prompt set ("buildings", "a lake",
# "a river", "flooded land", ...) scored 5/7 on the hand-checked probe in
# ``reality_check/probe_change_typing.py`` and over-predicted water on mixed
# urban tiles. Naming the urban case explicitly and making the water prompts
# describe an actual water body rather than a wet condition took it to 6/7.
# Re-run that probe before changing any line below.
CLASS_PROMPTS: dict[str, tuple[str, ...]] = {
    "built": (
        "a dense urban neighbourhood with many buildings",
        "rooftops of houses and apartment blocks",
        "an industrial facility",
        "a built-up city block",
        "newly built structures",
    ),
    "bare": (
        "bare ground",
        "cleared land",
        "an excavated site with bare soil",
        "dry barren land",
    ),
    "vegetation": (
        "dense forest",
        "trees and vegetation",
        "farmland with crops",
        "green fields",
    ),
    "water": (
        "a wide river channel",
        "a lake surrounded by land",
        "a reservoir of open water",
        "a canal of water",
    ),
    "road": (
        "a road",
        "a highway",
        "a paved road network",
        "a wide road corridor",
    ),
}

# Which covers must rise and which must fall for each supported change type.
# The four the problem statement names by name are first.
TYPE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "construction": {"up": ("built",), "down": ("bare", "vegetation")},
    "clearance": {"up": ("bare",), "down": ("vegetation", "built")},
    "water_increase": {"up": ("water",), "down": ("bare", "vegetation")},
    "water_decrease": {"up": ("bare", "vegetation"), "down": ("water",)},
    "road_development": {"up": ("road",), "down": ("vegetation", "bare")},
    "vegetation_regrowth": {"up": ("vegetation",), "down": ("bare",)},
}

PROMPT_TEMPLATE = "a satellite image of {}"

# A crop smaller than this carries too few pixels for the encoder to say
# anything honest about land cover, so it is left untyped instead.
MIN_CROP_PX = 24
# Margin a type must clear before it is named at all.
MIN_TYPE_SCORE = 0.05
# How strongly a cover must already be present around a region before the
# change counts as growth of an existing feature rather than a new one.
NEIGHBOUR_PRESENT = 0.25


class ChangeTyper:
    """Types candidate regions using an already-loaded retrieval engine.

    ``engine`` is the application's ``ClusterEngine``: this class borrows its
    loaded model, preprocessing transform and device rather than loading a
    second copy of a 600 MB checkpoint.
    """

    def __init__(self, engine):
        self.engine = engine
        self._class_vectors: np.ndarray | None = None
        self._class_names: list[str] = list(CLASS_PROMPTS)

    # -- model plumbing ----------------------------------------------------
    def _ensure_class_vectors(self) -> np.ndarray:
        """Encode the prompt groups once and keep them."""
        if self._class_vectors is not None:
            return self._class_vectors
        import open_clip
        import torch

        self.engine.load()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        vectors = []
        with torch.inference_mode():
            for name in self._class_names:
                prompts = [PROMPT_TEMPLATE.format(p) for p in CLASS_PROMPTS[name]]
                tokens = tokenizer(prompts).to(self.engine.device)
                encoded = self.engine.model.encode_text(tokens)
                encoded = encoded / encoded.norm(dim=-1, keepdim=True)
                mean = encoded.mean(dim=0)
                vectors.append((mean / mean.norm()).cpu().numpy())
        self._class_vectors = np.stack(vectors)
        return self._class_vectors

    def _class_probabilities(self, crops: list[Image.Image]) -> np.ndarray:
        """Softmax over the five cover groups, one row per crop."""
        import torch

        text = self._ensure_class_vectors()
        with torch.inference_mode():
            batch = torch.stack(
                [self.engine.preprocess(crop) for crop in crops]
            ).to(self.engine.device)
            encoded = self.engine.model.encode_image(batch)
            encoded = encoded / encoded.norm(dim=-1, keepdim=True)
            image = encoded.cpu().numpy()
        logits = 100.0 * image @ text.T
        logits -= logits.max(axis=1, keepdims=True)
        exponent = np.exp(logits)
        return exponent / exponent.sum(axis=1, keepdims=True)

    # -- geometry ----------------------------------------------------------
    @staticmethod
    def _crop(image: np.ndarray, box: list[int]) -> Image.Image | None:
        x0, y0, x1, y1 = box
        height, width = image.shape[:2]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        return Image.fromarray(image[y0:y1, x0:x1].astype(np.uint8))

    @classmethod
    def _neighbour_boxes(cls, box: list[int], shape: tuple) -> list[list[int]]:
        """Four same-sized patches touching the region, for the presence test."""
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        height, width = shape[:2]
        candidates = [
            [x0 - w, y0, x0, y1],
            [x1, y0, x1 + w, y1],
            [x0, y0 - h, x1, y0],
            [x0, y1, x1, y1 + h],
        ]
        return [
            b
            for b in candidates
            if b[0] >= 0 and b[1] >= 0 and b[2] <= width and b[3] <= height
        ]

    # -- typing ------------------------------------------------------------
    @staticmethod
    def _score_types(delta: dict[str, float]) -> dict[str, float]:
        """Rule table applied to the before/after probability difference."""
        scores = {}
        for name, rule in TYPE_RULES.items():
            rise = float(np.mean([delta[c] for c in rule["up"]]))
            fall = float(np.mean([-delta[c] for c in rule["down"]]))
            scores[name] = round(rise + 0.5 * fall, 4)
        return scores

    def _form(
        self,
        delta: dict[str, float],
        after_neighbours: np.ndarray | None,
        before_probability: dict[str, float],
    ) -> tuple[str, str]:
        """Appearance, disappearance, expansion or contraction, plus the reason."""
        risen = max(delta, key=delta.get)
        fallen = min(delta, key=delta.get)
        if delta[risen] < 0.05 and delta[fallen] > -0.05:
            return "undetermined", "no land-cover class moved decisively"
        if after_neighbours is None:
            return "undetermined", "no usable neighbourhood inside the analysis image"

        index = self._class_names.index(risen)
        around = float(after_neighbours[index])
        if delta[risen] >= abs(delta[fallen]):
            if around >= NEIGHBOUR_PRESENT:
                return (
                    "expansion",
                    f"{risen} rose inside the region and is already present around it "
                    f"({around:.2f})",
                )
            return (
                "appearance",
                f"{risen} rose inside the region and is largely absent around it "
                f"({around:.2f})",
            )
        if before_probability.get(fallen, 0.0) >= NEIGHBOUR_PRESENT:
            fallen_index = self._class_names.index(fallen)
            remaining = float(after_neighbours[fallen_index])
            if remaining >= NEIGHBOUR_PRESENT:
                return (
                    "contraction",
                    f"{fallen} fell inside the region but remains around it "
                    f"({remaining:.2f})",
                )
            return (
                "disappearance",
                f"{fallen} fell inside the region and is gone from around it "
                f"({remaining:.2f})",
            )
        return "undetermined", "the class that fell was not clearly present before"

    def type_region(
        self, before: np.ndarray, after: np.ndarray, box: list[int]
    ) -> dict | None:
        """Type and form for one candidate region, or None if it is too small."""
        x0, y0, x1, y1 = box
        if min(x1 - x0, y1 - y0) < MIN_CROP_PX:
            return None
        before_crop = self._crop(before, box)
        after_crop = self._crop(after, box)
        if before_crop is None or after_crop is None:
            return None

        crops = [before_crop, after_crop]
        neighbour_boxes = self._neighbour_boxes(box, after.shape)
        neighbour_crops = [self._crop(after, b) for b in neighbour_boxes]
        neighbour_crops = [c for c in neighbour_crops if c is not None]
        crops += neighbour_crops

        probabilities = self._class_probabilities(crops)
        before_p = dict(zip(self._class_names, probabilities[0].round(4).tolist()))
        after_p = dict(zip(self._class_names, probabilities[1].round(4).tolist()))
        neighbours = (
            probabilities[2:].mean(axis=0) if len(probabilities) > 2 else None
        )

        delta = {name: after_p[name] - before_p[name] for name in self._class_names}
        scores = self._score_types(delta)
        best = max(scores, key=scores.get)
        ordered = sorted(scores.values(), reverse=True)
        margin = round(ordered[0] - ordered[1], 4) if len(ordered) > 1 else 0.0
        named = best if scores[best] > MIN_TYPE_SCORE else "other"
        form, reason = self._form(delta, neighbours, before_p)

        return {
            "type": named,
            "type_scores": scores,
            "type_margin": margin,
            "form": form,
            "form_reason": reason,
            "before_classes": before_p,
            "after_classes": after_p,
            "neighbourhood_classes": (
                dict(zip(self._class_names, neighbours.round(4).tolist()))
                if neighbours is not None
                else None
            ),
            "method": "zero-shot RemoteCLIP land-cover prompt delta",
            "validated": False,
        }

    def type_regions(
        self, before: np.ndarray, after: np.ndarray, regions: list[dict], limit: int = 12
    ) -> dict:
        """Type the largest regions and summarise what was found.

        Only the largest ``limit`` regions are typed: a candidate list can hold
        a hundred specks, and encoding every one of them would cost more than
        the answer is worth.
        """
        typed = 0
        skipped = 0
        for region in regions[:limit]:
            try:
                result = self.type_region(before, after, region["bbox_pixels"])
            except Exception as exc:  # noqa: BLE001 - recorded, never raised upward
                region["typing_error"] = f"{type(exc).__name__}: {exc}"
                skipped += 1
                continue
            if result is None:
                region["type"] = "untyped"
                region["type_reason"] = (
                    f"region smaller than {MIN_CROP_PX}px on a side"
                )
                skipped += 1
                continue
            region.update(result)
            typed += 1
        for region in regions[limit:]:
            region["type"] = "untyped"
            region["type_reason"] = f"outside the {limit} largest regions"

        counts: dict[str, int] = {}
        forms: dict[str, int] = {}
        for region in regions:
            if region.get("type") and region["type"] != "untyped":
                counts[region["type"]] = counts.get(region["type"], 0) + 1
            if region.get("form"):
                forms[region["form"]] = forms.get(region["form"], 0) + 1

        dominant = max(counts, key=counts.get) if counts else None
        return {
            "regions_typed": typed,
            "regions_skipped": skipped,
            "types": counts,
            "forms": forms,
            "dominant_type": dominant,
            "method": "zero-shot RemoteCLIP land-cover prompt delta",
            "validated": False,
            "note": (
                "Types and forms are zero-shot land-cover inferences, not "
                "validated detections. No independent labelled set has scored "
                "them yet."
            ),
        }
