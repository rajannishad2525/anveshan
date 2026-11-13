from app.spatial import filter_rows

"""Local-only imagery screening and conservative visual clustering.

No filename/location inference. Similarity is not a calibrated probability.
Model weights must already be installed; this module never downloads them.
"""
import hashlib
import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

import numpy as np
from PIL import Image, ImageStat
from app.place_matching import local_features, group_places, period_info, verify_place


def runtime_preprocess(image):
    """Exact PIL RGB evaluation transform, without importing training libraries."""
    import torch

    w, h = image.size
    if min(w, h) != 224:
        size = (224, int(224 * h / w)) if w <= h else (int(224 * w / h), 224)
        image = image.resize(size, Image.Resampling.BICUBIC)
    w, h = image.size
    left, top = int(round((w - 224) / 2)), int(round((h - 224) / 2))
    image = image.crop((left, top, left + 224, top + 224)).convert("RGB")
    tensor = torch.from_numpy(np.array(image, dtype=np.uint8, copy=True)).permute(2, 0, 1).contiguous().to(dtype=torch.float32).div(255)
    mean = torch.tensor((0.48145466, 0.4578275, 0.40821073)).view(-1, 1, 1)
    std = torch.tensor((0.26862954, 0.26130258, 0.27577711)).view(-1, 1, 1)
    return tensor.sub_(mean).div_(std)

POSITIVE = [
    f"an aerial photograph of {x}"
    for x in (
        "buildings and roads",
        "farmland and fields",
        "a river and vegetation",
        "a forest",
        "a desert",
        "an airport",
        "a harbour",
        "mountains",
        "a city",
        "the ocean",
    )
] + [
    "a satellite image",
    "an aerial image",
    "an overhead satellite view of the ground",
    "a high resolution satellite map showing terrain and buildings",
]
NEGATIVE = [
    "a company logo on a plain background",
    "a graphic icon or symbol",
    "a screenshot of a website",
    "a page of text in a document",
    "a ground level photograph of people on a street",
    "a portrait of a person",
    "a cartoon drawing",
    "a chart or diagram",
    "a labelled street map",
]
THRESHOLD = 0.90  # Provisional conservative operating point, not 90% accuracy.
INDEX_REVISION = 3
# RemoteCLIP takes a 224 px input. A 1024 px scene at 10 m covers 10.24 km, so
# resizing the whole scene to 224 hands the model ~46 m per pixel - far outside
# its RSICD/RSITMD training domain. Embedding 224 px windows at native GSD
# doubled top-1 on the 12-query probe (reality_check/tiling_ab.py).
TILE_PX = 224
# Scene score is the mean of its best TILE_TOP_K windows. 1 (pure max) lets a
# single noisy window win; the whole-scene mean buries a small real target.
TILE_TOP_K = 3
# Weight on land-cover agreement between the query and a window, on top of the
# plain cosine. Measured on the 12-query probe (reality_check/hybrid_scoring.py):
#   0.00  top-1 0.333  top-5 0.667      0.10  top-1 0.250  top-5 0.833
#   0.05  top-1 0.333  top-5 0.750      0.20  top-1 0.083  top-5 0.750
# 0.05 is the only setting that beats plain cosine without costing top-1.
COVER_WEIGHT = 0.05


def refine_query(query, vectors):
    """Small, explicit positive-relevance shift; never changes stored vectors."""
    if len(vectors) < 5:
        raise ValueError(
            "Select at least five distinct indexed observations relevant to this text query"
        )
    centroid = np.mean(vectors, axis=0)
    if not np.isfinite(centroid).all() or np.linalg.norm(centroid) < 1e-8:
        raise ValueError("Selected feedback has no usable direction")
    shifted = 0.85 * query + 0.15 * centroid / np.linalg.norm(centroid)
    return (shifted / np.linalg.norm(shifted)).astype("float32")


def retain_observation(accepted, seen, key, scene):
    """Prefer a real georeferenced twin; never transfer geometry onto a PNG."""
    if key not in seen:
        seen[key] = len(accepted)
        accepted.append(scene)
        return False
    position = seen[key]
    previous = accepted[position]
    if scene.get("geometry") and not previous.get("geometry"):
        scene["duplicate_scene_ids"] = previous.get("duplicate_scene_ids", []) + [
            previous["id"]
        ]
        accepted[position] = scene
    else:
        previous.setdefault("duplicate_scene_ids", []).append(scene["id"])
    return True


def _rgb_via_pil(source):
    with Image.open(source) as image:
        image.thumbnail((1024, 1024))
        return image.convert("RGB").copy()


def _rgb_via_rasterio(source):
    import rasterio

    with rasterio.open(source) as src:
        bands = list(range(1, min(3, src.count) + 1))
        a = src.read(
            bands,
            out_shape=(len(bands), min(1024, src.height), min(1024, src.width)),
        )
        if len(bands) < 3:
            a = np.repeat(a[:1], 3, axis=0)
        if a.dtype != np.uint8:
            a = a.astype("float32")
            for channel in a:
                # The 2/98 stretch bounds are read off every 3rd pixel: 116k
                # samples instead of 1M on a 1024x1024 band. Measured over 10
                # Sentinel-2 scenes from this archive, the decoded pixels move
                # by 0.16 DN on average and never more than 1 DN of 255 - below
                # the uint8 rounding already applied below.
                lo, hi = np.nanpercentile(channel[::3, ::3], (2, 98))
                channel[:] = np.clip((channel - lo) / max(hi - lo, 1e-6), 0, 1) * 255
        return Image.fromarray(np.moveaxis(np.nan_to_num(a).astype("uint8"), 0, -1))


def read_rgb(path):
    """Decode any supported source to an RGB image, longest side <= 1024 px.

    GeoTIFFs are handed to rasterio first. PIL cannot even *identify* a 5-band
    uint16 Sentinel-2 scene - which is most of a real archive - but spends
    ~70 ms per file probing its plugins before saying so. PIL stays as the
    fallback for the plain 8-bit TIFFs it does handle.
    """
    name = path if isinstance(path, (str, Path)) else ""
    geotiff = Path(name).suffix.lower() in (".tif", ".tiff") if name else False
    readers = (
        (_rgb_via_rasterio, _rgb_via_pil) if geotiff else (_rgb_via_pil, _rgb_via_rasterio)
    )
    failure = None
    for reader in readers:
        try:
            return reader(path)
        except Exception as exc:
            failure = exc
            if hasattr(path, "seek"):
                path.seek(0)
    raise failure


def tile_windows(image, tile=TILE_PX):
    """(crop, row, col) for each native-resolution window, row-major.

    Positions are kept because "near a river" needs neighbouring windows, not
    just the window itself.
    """
    width, height = image.size
    if width < tile or height < tile:
        return [(image, 0, 0)]
    out = [
        (image.crop((x, y, x + tile, y + tile)), row, col)
        for row, y in enumerate(range(0, height - tile + 1, tile))
        for col, x in enumerate(range(0, width - tile + 1, tile))
    ]
    return out or [(image, 0, 0)]


def tile_images(image, tile=TILE_PX):
    """Non-overlapping native-resolution windows; whole image if it is smaller."""
    return [crop for crop, _, _ in tile_windows(image, tile)]


def water_fraction_grid(path, tile=TILE_PX, shape=None):
    """Water coverage per tile window, from the SCL band. None when absent.

    SCL class 6 is water of any kind - river, lake, reservoir, sea. This
    measures proximity to water, not to a river specifically.
    """
    import rasterio
    from app.spectral import WATER, scl_band_index

    with rasterio.open(path) as src:
        band = scl_band_index(src)
        if band is None:
            return None
        height, width = (shape or (src.height, src.width))
        scl = src.read(band, out_shape=(height, width),
                       resampling=rasterio.enums.Resampling.nearest)
    if width < tile or height < tile:
        return {(0, 0): float(np.isin(scl, WATER).mean())}
    grid = {}
    for row, y in enumerate(range(0, height - tile + 1, tile)):
        for col, x in enumerate(range(0, width - tile + 1, tile)):
            window = scl[y:y + tile, x:x + tile]
            grid[(row, col)] = float(np.isin(window, WATER).mean())
    return grid


# A window counts as holding water at this coverage; below it the SCL hits are
# usually wet field edges, not a water body.
WATER_MIN = 0.05


def near_water_mask(cells, minimum=None):
    """True for each window that holds water or touches one that does.

    "Near" is one window: at 224 px and 10 m that is 2.24 km. SCL class 6 does
    not distinguish a river from a lake or the sea, so this is proximity to
    water, not to a river.
    """
    minimum = WATER_MIN if minimum is None else float(minimum)
    wet = {(sid, row, col) for sid, row, col, water in cells if water >= minimum}
    out = []
    for sid, row, col, water in cells:
        near = water >= minimum or any(
            (sid, row + dr, col + dc) in wet
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr, dc) != (0, 0)
        )
        out.append(near)
    return out


def compatible_footprints(a, b):
    """Veto a visual match when embedded georeferencing contradicts it."""
    if not a.get("geometry") or not b.get("geometry"):
        return True
    ga, gb = a["geometry"], b["geometry"]
    if ga["crs"] != gb["crs"]:
        return False  # Reprojection/registration required before grouping.
    x1, y1, x2, y2 = ga["bounds"]
    u1, v1, u2, v2 = gb["bounds"]
    overlap = max(0, min(x2, u2) - max(x1, u1)) * max(0, min(y2, v2) - max(y1, v1))
    union = (x2 - x1) * (y2 - y1) + (u2 - u1) * (v2 - v1) - overlap
    return union > 0 and overlap / union >= 0.90


def _softmax(x, axis=-1):
    """Sharpened cover profile; the 100x matches CLIP's logit scale."""
    x = x - x.max(axis=axis, keepdims=True)
    e = np.exp(x * 100.0)
    return e / e.sum(axis=axis, keepdims=True)


def conservative_groups(vectors, threshold=THRESHOLD, scenes=None):
    """FAISS candidate discovery + all-member check prevents DBSCAN chaining.

    Every returned group's pairwise cosine is >= threshold. Candidate search is
    capped at 64 neighbours; large groups may split rather than merge loosely.
    """
    import faiss

    if len(vectors) < 2:
        return [], list(range(len(vectors)))
    x = np.ascontiguousarray(vectors, dtype="float32")
    faiss.normalize_L2(x)
    index = faiss.IndexHNSWFlat(x.shape[1], 32, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = 100
    index.hnsw.efSearch = 128
    index.add(x)
    scores, neighbours = index.search(x, min(64, len(x)))
    assigned, groups, singles = set(), [], []
    for seed in range(len(x)):
        if seed in assigned:
            continue
        members = [seed]
        for score, candidate in zip(scores[seed], neighbours[seed]):
            candidate = int(candidate)
            if (
                candidate < 0
                or candidate == seed
                or candidate in assigned
                or score < threshold
            ):
                continue
            if scenes is not None and not all(
                compatible_footprints(scenes[i], scenes[candidate]) for i in members
            ):
                continue
            if float(np.min(x[members] @ x[candidate])) >= threshold:
                members.append(candidate)
        assigned.update(members)
        if len(members) > 1:
            groups.append(members)
        else:
            singles.append(seed)
    return groups, singles


class ClusterEngine:
    def __init__(self, root, connect):
        self.root, self.connect = Path(root), connect
        import os

        self.data = Path(
            os.environ.get("ANVESHAN_DATA_DIR", str(self.root / "datasets"))
        )
        self.guard = threading.RLock()
        self.signature = None
        self.running = False
        self.groups = []
        self.similar_sites = []
        self.status = {"state": "waiting", "done": 0, "total": 0}
        self.model = None
        self.build_requested = False
        try:
            saved = json.loads(
                (self.data / "cluster_state.json").read_text(encoding="utf-8")
            )
            rows = self.snapshot()
            signature = hashlib.sha256(
                json.dumps(
                    [(r["id"], r["path"], r["sha256"], r["imported_at"]) for r in rows]
                ).encode()
            ).hexdigest()
            if (
                saved["signature"] == signature
                and saved.get("index_revision") == INDEX_REVISION
            ):
                self.signature = signature
                self.groups = saved["groups"]
                self.similar_sites = saved["similar_sites"]
                self.status = saved["status"]
                self.build_requested = True
        except (OSError, ValueError, KeyError):
            pass

    def snapshot(self):
        c = self.connect()
        try:
            return [
                dict(r)
                for r in c.execute(
                    "select * from scenes where status='ready' order by id"
                )
            ]
        finally:
            c.close()

    def ensure(self):
        if not self.build_requested:
            return
        rows = self.snapshot()
        signature = hashlib.sha256(
            json.dumps(
                [(r["id"], r["path"], r["sha256"], r["imported_at"]) for r in rows]
            ).encode()
        ).hexdigest()
        with self.guard:
            if self.running or self.signature == signature:
                return
            self.signature = signature
            self.groups = []
            self.similar_sites = []
            if not rows:
                self.status = {
                    "state": "ready",
                    "done": 0,
                    "total": 0,
                    "groups": 0,
                    "unmatched": 0,
                    "review": [],
                    "excluded": 0,
                }
                return
            self.running = True
            self.status = {
                "state": "loading local model",
                "done": 0,
                "total": len(rows),
            }
            threading.Thread(target=self.run, args=(rows,), daemon=True).start()

    def rebuild(self):
        """Start a deliberate operator-requested rebuild.

        Importing files only changes the archive. This method is the explicit
        gate for screening, embedding and clustering.
        """
        with self.guard:
            if self.running:
                return
            self.build_requested = True
            self.signature = None
        self.ensure()

    def clear(self):
        """Forget all derived clustering state after the archive is cleared."""
        with self.guard:
            (self.data / "cluster_state.json").unlink(missing_ok=True)
            self.build_requested = False
            self.signature = None
            self.groups = []
            self.similar_sites = []
            self.running = False
            self.status = {
                "state": "waiting",
                "done": 0,
                "total": 0,
                "groups": 0,
                "unmatched": 0,
                "review": [],
                "excluded": 0,
            }

    def load(self):
        if self.model is not None:
            return
        self.status.update(current="Starting local CPU inference library")
        import torch

        weights = self.root / "models/RemoteCLIP-ViT-B-32.pt"
        if not weights.exists():
            raise RuntimeError(
                "Offline RemoteCLIP checkpoint missing. Ask the installer to restore it."
            )
        # One thread per physical core. cpu_count() reports logical cores, and
        # oneDNN gets slower past the physical count on a hyper-threaded CPU.
        # Floor of 4 keeps the previously measured behaviour on this 4-core box;
        # a 16-core workstation is no longer capped at 4.
        import os

        torch.set_num_threads(max(4, (os.cpu_count() or 8) // 2))
        self.device = "cpu"
        self.status.update(current="Reading local model weights")
        runtime = self.root / "models/remoteclip-runtime.pt"
        manifest_path = self.root / "models/remoteclip-runtime.json"
        if runtime.exists() and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if (manifest.get("weight_size") == weights.stat().st_size
                    and manifest.get("prompts") == POSITIVE + NEGATIVE
                    and manifest.get("torch") == torch.__version__):
                self.status.update(current="Checking local model bundle")
                # Installer timestamps have two-second resolution. Checksums
                # are recorded at export; do not reread 1.2 GB on every launch.
                for file, prefix in ((weights, "weight"), (runtime, "runtime")):
                    stat = file.stat()
                    if (stat.st_size != manifest.get(prefix + "_size") or
                            stat.st_mtime_ns // 2_000_000_000 != manifest.get(prefix + "_mtime_ns", 0) // 2_000_000_000):
                        raise RuntimeError("Local inference bundle is stale. Restore the model bundle using the installer.")
                self.preprocess = runtime_preprocess
                self.model = torch.jit.load(str(runtime), map_location="cpu").eval()
                self.text = np.load(self.root / "models/remoteclip-screen.npy", allow_pickle=False)
                return
        self.status.update(current="Preparing local model architecture")
        import open_clip
        model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained=None
        )
        model.load_state_dict(
            torch.load(weights, map_location="cpu", weights_only=True)
        )
        model.eval()
        model.to(self.device)
        with torch.inference_mode():
            text = model.encode_text(
                open_clip.get_tokenizer("ViT-B-32")(POSITIVE + NEGATIVE).to(self.device)
            )
            self.text = (text / text.norm(dim=-1, keepdim=True)).cpu().numpy()
        self.model = model

    # Prompt ensembling is the textbook fix for unstable CLIP text vectors, and
    # it did help marginally while the model was being fed a whole 10 km scene
    # squashed to 224 px. Measured again on 224 px tiles it is worse and four
    # times slower, so the default is the bare query:
    #   1 template   top-1 0.333  top-5 0.667   ~94 ms
    #   6 templates  top-1 0.333  top-5 0.583   ~407 ms
    # See reality_check/prompt_templates.json. The extras stay here so the
    # comparison can be rerun, not because they are switched on.
    TEXT_TEMPLATES = ("{}",)
    TEXT_TEMPLATES_ENSEMBLE = (
        "{}",
        "a satellite image of {}",
        "an aerial photograph of {}",
        "a remote sensing image showing {}",
        "satellite imagery of {}",
        "a top-down view of {}",
    )
    TEXT_CACHE_SIZE = 128

    def encode_text(self, query: str, templates=None):
        """Unit-norm text vector. Repeat queries come from a small cache."""
        templates = tuple(templates or self.TEXT_TEMPLATES)
        key = (query.strip(), templates)
        cache = getattr(self, "_text_cache", None)
        if cache is None:
            cache = self._text_cache = {}
        if key in cache:
            return cache[key]

        import open_clip
        import torch

        prompts = [t.format(query.strip()) for t in templates]
        with torch.inference_mode():
            tokens = open_clip.get_tokenizer("ViT-B-32")(prompts).to(self.device)
            value = self.model.encode_text(tokens)
            value = value / value.norm(dim=-1, keepdim=True)
            pooled = value.mean(dim=0)
            pooled = pooled / pooled.norm()
        vector = pooled.cpu().numpy().astype("float32")
        if len(cache) >= self.TEXT_CACHE_SIZE:
            cache.pop(next(iter(cache)))
        cache[key] = vector
        return vector


    def run(self, rows):
        import time

        started = time.perf_counter()
        self.status.update(total=len(rows), started_at=time.time(), current="Starting local CPU inference library")
        cache = None
        try:
            self.load()
            model_loaded = time.perf_counter()
            import torch

            weights = self.root / "models/RemoteCLIP-ViT-B-32.pt"
            version = f"remoteclip-b32-screen-v1-{weights.stat().st_size}-{weights.stat().st_mtime_ns}"
            cache = sqlite3.connect(self.data / "semantic_cache.sqlite3")
            cache.execute(
                "create table if not exists features(key text primary key, vector blob, positive real, negative real)"
            )
            cache.execute(
                "create table if not exists scene_features(scene_id integer primary key, vector blob not null, model text not null)"
            )
            cache.execute(
                "create table if not exists tile_features(scene_id integer not null,"
                " tile_index integer not null, row integer not null, col integer not null,"
                " water_fraction real not null, vector blob not null, model text not null,"
                " primary key(scene_id, tile_index))"
            )
            accepted, vectors, review, seen = [], [], [], {}
            digests = {}
            duplicates = 0
            self.status.update(state="screening and embedding")
            for n, scene in enumerate(rows):
                try:
                    scene.update(period_info(scene["path"], scene.get("date")))
                    if Path(scene["path"]).suffix.lower() in (".tif", ".tiff"):
                        import rasterio

                        with rasterio.open(scene["path"]) as src:
                            if src.crs:
                                scene["geometry"] = {
                                    "crs": str(src.crs),
                                    "bounds": list(src.bounds),
                                }
                    image = read_rgb(scene["path"])
                    # Operator screenshots and browser captures can contain
                    # satellite thumbnails, so the vision model may score
                    # them as aerial imagery. Imported scene tiles are square
                    # rasters; reject oversized photographic/UI frames before
                    # semantic screening and keep them in the review queue.
                    suffix = Path(scene["path"]).suffix.lower()
                    if (
                        suffix in (".png", ".jpg", ".jpeg", ".webp")
                        and max(image.size) > 1024
                    ):
                        raise ValueError(
                            "Oversized screenshot or browser capture: withheld before clustering"
                        )
                    if max(image.size) / max(1, min(image.size)) > 4:
                        raise ValueError(
                            "Very wide/tall image or contact sheet: review before scene clustering"
                        )
                    if min(image.size) < 64 or max(ImageStat.Stat(image).stddev) < 4:
                        raise ValueError(
                            "Blank, low-detail or too small to assess as satellite imagery"
                        )
                    digest = hashlib.sha256(
                        str(image.size).encode() + image.tobytes()
                    ).hexdigest()
                    key = version + digest
                    hit = cache.execute(
                        "select vector,positive,negative from features where key=?",
                        (key,),
                    ).fetchone()
                    if hit:
                        vector, positive, negative = (
                            np.frombuffer(hit[0], dtype="float32"),
                            hit[1],
                            hit[2],
                        )
                    else:
                        with torch.inference_mode():
                            value = self.model.encode_image(
                                self.preprocess(image).unsqueeze(0).to(self.device)
                            )
                            vector = (
                                (value / value.norm(dim=-1, keepdim=True))
                                .cpu()
                                .numpy()[0]
                                .astype("float32")
                            )
                        similarities = self.text @ vector
                        positive, negative = float(
                            max(similarities[: len(POSITIVE)])
                        ), float(max(similarities[len(POSITIVE) :]))
                        cache.execute(
                            "insert or replace into features values(?,?,?,?)",
                            (key, vector.tobytes(), positive, negative),
                        )
                        cache.commit()
                    # Re-evaluate prompts against cached vectors when screening changes.
                    similarities = self.text @ vector
                    positive, negative = float(
                        max(similarities[: len(POSITIVE)])
                    ), float(max(similarities[len(POSITIVE) :]))
                    scene["screening_margin"] = round(positive - negative, 4)
                    # A weak global text score must not discard changed/seasonal
                    # imagery. Only strong negative evidence is excluded here;
                    # uncertain candidates need a verified place link later.
                    if positive < 0.20 or positive - negative < -0.035:
                        raise ValueError(
                            "Non-satellite or uncertain imagery: withheld for review"
                        )
                    observation_key = (digest, scene["period_label"])
                    digests[scene["id"]] = digest
                    if retain_observation(accepted, seen, observation_key, scene):
                        duplicates += 1
                    else:
                        vectors.append(vector)
                except Exception as exc:
                    review.append(
                        {"id": scene["id"], "name": scene["name"], "reason": str(exc)}
                    )
                self.status.update(
                    done=n + 1,
                    accepted=len(accepted),
                    excluded=len(review),
                    duplicates=duplicates,
                )
            self.status.update(state="verifying same-location matches")
            screened = time.perf_counter()

            # RootSIFT is only consulted for candidate pairs where at least one
            # side has no georeferencing. On a GeoTIFF archive that never
            # happens, so computing it for every scene up front burns ~0.3 s
            # each for a result nothing reads. Compute per scene on demand.
            structural = {}

            def features_for(i):
                if i not in structural:
                    structural[i] = local_features(read_rgb(accepted[i]["path"]))
                return structural[i]

            memberships, singles, links = group_places(
                accepted, vectors, features_for, compatible_footprints
            )
            verified = time.perf_counter()
            self.status.update(state="building temporal groups", current="Collecting verified relationships")
            groups = []
            for members in memberships:
                scenes = sorted(
                    [accepted[i] for i in members],
                    key=lambda s: (s["period_start"], s["id"]),
                )
                x = np.asarray([vectors[i] for i in members])
                key = (
                    "place-"
                    + hashlib.sha256(
                        ",".join(str(s["id"]) for s in scenes).encode()
                    ).hexdigest()[:12]
                )
                groups.append(
                    {
                        "key": key,
                        "count": len(scenes),
                        "scenes": scenes,
                        "dates": list(dict.fromkeys(s["period_label"] for s in scenes)),
                        "method": "same-location: embedded footprints or RootSIFT/RANSAC verified links",
                        "evidence": [
                            {
                                "before": accepted[i]["id"],
                                "after": accepted[j]["id"],
                                **proof,
                            }
                            for i, j, proof in links
                            if i in members and j in members
                        ],
                        "minimum_similarity": round(float(np.min(x @ x.T)), 4),
                        "location_verified": all(s.get("geometry") for s in scenes),
                    }
                )
            # PS 2.2.4: discover comparable sites, kept separate from temporal
            # observations of one site. Use one representative per place.
            representatives = [members[0] for members in memberships] + singles
            similar_members, _ = conservative_groups(
                [vectors[i] for i in representatives]
            )
            similar_sites = []
            for members in similar_members:
                items = [accepted[representatives[i]] for i in members]
                key = (
                    "sites-"
                    + hashlib.sha256(
                        ",".join(str(s["id"]) for s in items).encode()
                    ).hexdigest()[:12]
                )
                similar_sites.append(
                    {
                        "key": key,
                        "scenes": items,
                        "count": len(items),
                        "dates": sorted({s["date"] for s in items if s.get("date")}),
                        "method": "RemoteCLIP similar-site discovery; not a temporal group",
                        "location_verified": False,
                    }
                )
            # Publish the current representatives together, removing stale/duplicate IDs.
            with cache:
                cache.execute("delete from scene_features")
                cache.executemany(
                    "insert into scene_features values(?,?,?)",
                    [
                        (scene["id"], vector.tobytes(), version)
                        for scene, vector in zip(accepted, vectors)
                    ],
                )
            self.build_tile_features(accepted, version, digests)
            with self.guard:
                self._rank_version = None
                self.groups = groups
                self.similar_sites = similar_sites
                self.status.update(
                    state="ready",
                    groups=len(groups),
                    unmatched=len(singles),
                    review=review,
                    build_seconds=round(time.perf_counter() - started, 3),
                    stage_seconds={"model": round(model_loaded-started,3),
                                   "screening": round(screened-model_loaded,3),
                                   "verification": round(verified-screened,3),
                                   "groups_and_tiles": round(time.perf_counter()-verified,3)},
                    similar_site_groups=len(similar_sites),
                    unmatched_scene_ids=[accepted[i]["id"] for i in singles],
                    grouping="same-location temporal groups",
                    encoder="RemoteCLIP ViT-B-32",
                    device=self.device,
                    accuracy="Not yet measured on labelled evaluation set",
                )
                temporary = self.data / "cluster_state.tmp"
                temporary.write_text(
                    json.dumps(
                        {
                            "index_revision": INDEX_REVISION,
                            "signature": self.signature,
                            "groups": groups,
                            "similar_sites": similar_sites,
                            "status": self.status,
                        }
                    ),
                    encoding="utf-8",
                )
                temporary.replace(self.data / "cluster_state.json")
        except Exception as exc:
            self.status.update(state="error", error=str(exc))
        finally:
            if cache is not None:
                cache.close()
            with self.guard:
                self.running = False
            # A folder added while processing is picked up automatically.
            self.ensure()

    def search(
        self,
        query="",
        reference_id=None,
        date_from="",
        date_to="",
        kind="",
        limit=30,
        sensor="",
        bbox="",
        feedback_ids=None,
        near_water=False,
        water_min=None,
        cover_weight=COVER_WEIGHT,
    ):
        """Offline semantic text/image retrieval over the cached scene vectors."""
        if self.status.get("state") != "ready":
            raise ValueError("Press BUILD LOCAL INDEX and wait for it to complete")
        self.ensure()
        self.load()
        import torch, open_clip

        if reference_id is not None:
            if feedback_ids:
                raise ValueError(
                    "Relevance refinement is available for text queries only"
                )
            c = self.connect()
            reference = c.execute(
                "select path from scenes where id=? and status='ready'",
                (int(reference_id),),
            ).fetchone()
            c.close()
            if not reference:
                raise ValueError("Reference image is not in the active archive")
            return self.search_image(
                read_rgb(reference["path"]),
                date_from,
                date_to,
                kind,
                limit,
                sensor,
                bbox,
            )
        else:
            if not query.strip():
                raise ValueError("Enter text or choose a reference image")
            query_vector = self.encode_text(query)
            mode = "free-text"
        if feedback_ids:
            active = {r["id"] for r in self.snapshot()}
            requested = set(feedback_ids)
            if not requested <= active:
                raise ValueError("Feedback contains imagery outside the active archive")
            with closing(
                sqlite3.connect(self.data / "semantic_cache.sqlite3")
            ) as cache:
                stored = dict(
                    cache.execute("select scene_id,vector from scene_features")
                )
            aliases = {
                duplicate: s["id"]
                for g in self.groups
                for s in g["scenes"]
                for duplicate in s.get("duplicate_scene_ids", [])
            }
            canonical = {aliases.get(sid, sid) for sid in requested}
            if not canonical <= stored.keys():
                raise ValueError(
                    "Some selected images were withheld from the visual index"
                )
            query_vector = refine_query(
                query_vector,
                [
                    np.frombuffer(stored[sid], dtype="float32")
                    for sid in sorted(canonical)
                ],
            )
        c = self.connect()
        rows = [dict(r) for r in c.execute("select * from scenes where status='ready'")]
        c.close()
        if kind:
            rows = [r for r in rows if r.get("kind") == kind]
        rows = filter_rows(rows, sensor, bbox, date_from, date_to)
        scored = []
        for row, score in self.rank_vectors(rows, query_vector, near_water=near_water,
                                          water_min=water_min,
                                          cover_weight=cover_weight):
            row["match_score"] = round(max(0, min(1, score)), 4)
            row["score_type"] = "RemoteCLIP cosine similarity"
            row["search_mode"] = mode
            row["reference_scene_id"] = reference_id
            scored.append(row)
        return {
            "query": query,
            "reference_scene_id": reference_id,
            "results": scored[: max(1, min(int(limit), 200))],
            "method": "offline RemoteCLIP image-text embedding search",
            "encoder": "RemoteCLIP ViT-B-32",
            "semantic": True,
            "mode": mode,
            "feedback_applied": bool(feedback_ids),
            "note": "Similarity is a ranking score, not a calibrated accuracy percentage.",
            "spatial_relation": {
                "near_water": bool(near_water),
                "water_min": float(WATER_MIN if water_min is None else water_min),
                "window_km": round(TILE_PX * 10 / 1000, 2),
                "source": "Sentinel-2 SCL class 6",
                "caveat": "SCL water does not separate river from lake or sea;"
                          " this is proximity to water, not to a river.",
            } if near_water else None,
        }

    def search_image(
        self, image, date_from="", date_to="", kind="", limit=30, sensor="", bbox=""
    ):
        """Image-to-image search for an uploaded reference; original is never archived."""
        if self.status.get("state") != "ready":
            raise ValueError("Press BUILD LOCAL INDEX and wait for it to complete")
        self.ensure()
        self.load()
        import torch

        query_features = local_features(image)
        with torch.inference_mode():
            value = self.model.encode_image(
                self.preprocess(image).unsqueeze(0).to(self.device)
            )
            query_vector = (value / value.norm(dim=-1, keepdim=True)).cpu().numpy()[0]
        c = self.connect()
        rows = [dict(r) for r in c.execute("select * from scenes where status='ready'")]
        c.close()
        if kind:
            rows = [r for r in rows if r.get("kind") == kind]
        rows = filter_rows(rows, sensor, bbox, date_from, date_to)
        candidates = []
        for row, score in self.rank_vectors(rows, query_vector, 60):
            row["_semantic"] = score
            candidates.append(row)
        # RemoteCLIP is a retrieval cue, not an identity test. Verify the
        # strongest candidates against local image structure and rank those
        # exact-place matches first. Do not discard the remaining visual
        # neighbours: an uploaded crop, rescaled export or genuinely similar
        # site may not have enough shared keypoints for a same-place proof.
        scored = []
        for row in candidates[:60]:
            structural = False
            proof = {}
            try:
                proof = verify_place(
                    query_features, local_features(read_rgb(row["path"]))
                )
                structural = bool(proof.get("matched"))
            except (OSError, ValueError):
                proof = {"matched": False, "method": "RootSIFT + RANSAC"}
            semantic = row.pop("_semantic")
            row["match_score"] = round(max(0, min(1, semantic)), 4)
            row["score_type"] = (
                "RemoteCLIP + RootSIFT structural match"
                if structural
                else "RemoteCLIP cosine visual similarity (unverified)"
            )
            row["structural_match"] = structural
            row["structural_evidence"] = proof
            row["search_mode"] = "uploaded-image"
            scored.append(row)
        scored.sort(
            key=lambda r: (not r["structural_match"], -r["match_score"], r["name"])
        )
        scored = self.expand_temporal_results(scored, rows)
        return {
            "query": "uploaded reference image",
            "results": scored[: max(1, min(int(limit), 200))],
            "method": "offline visual retrieval; structurally verified matches ranked first",
            "encoder": "RemoteCLIP ViT-B-32",
            "semantic": True,
            "mode": "image-to-image",
            "note": "Unverified visual matches are retrieval cues. Timeline members may not directly match the reference. Scores are not accuracy percentages.",
        }

    TILE_COLUMNS = [
        "scene_id", "tile_index", "row", "col", "water_fraction", "vector", "model",
    ]

    def build_tile_features(self, accepted, version, digests, batch=32):
        """One vector per 224 px window, so a 10 km scene is not squashed to 224 px.

        Each row is stamped with the encoder version *and* the scene's pixel
        digest, so a scene whose bytes have not changed keeps its cached
        vectors. Re-encoding an unchanged 121-scene archive costs ~2 minutes of
        CPU to arrive at identical numbers.
        """
        import torch

        path = self.data / "semantic_cache.sqlite3"
        stamp = {
            scene["id"]: f"{version}|{digests.get(scene['id'], '')}"
            for scene in accepted
        }
        with closing(sqlite3.connect(path)) as cache:
            columns = [r[1] for r in cache.execute("pragma table_info(tile_features)")]
            if columns and columns != self.TILE_COLUMNS:
                # Derived cache: drop rather than migrate when the columns change.
                cache.execute("drop table if exists tile_features")
            cache.execute(
                "create table if not exists tile_features(scene_id integer not null,"
                " tile_index integer not null, row integer not null, col integer not null,"
                " water_fraction real not null, vector blob not null, model text not null,"
                " primary key(scene_id, tile_index))"
            )
            reusable = sorted(
                scene_id
                for scene_id, model in cache.execute(
                    "select distinct scene_id, model from tile_features"
                )
                if stamp.get(scene_id) == model
            )
            with cache:
                if reusable:
                    cache.execute(
                        "delete from tile_features where scene_id not in (%s)"
                        % ",".join("?" * len(reusable)),
                        reusable,
                    )
                else:
                    cache.execute("delete from tile_features")
        fresh = set(reusable)

        rows = []
        # ponytail: a scene that yields no rows (single window, or unreadable) is
        # re-decoded on every build because there is nothing to match against.
        # Those are the cheap ones; add a processed-scenes marker if that changes.
        pending = [scene for scene in accepted if scene["id"] not in fresh]
        self.status.update(state="encoding local tiles", tile_scenes_total=len(pending), tile_scenes_done=0)
        for scene_number, scene in enumerate(pending):
            self.status.update(tile_scenes_done=scene_number, current=f"Reading tiles for scene {scene['id']}")
            try:
                image = read_rgb(scene["path"])
            except Exception:
                continue  # unreadable source is already flagged at intake
            windows = tile_windows(image)
            if len(windows) < 2:
                continue  # a single window adds nothing over the scene vector
            try:
                water = water_fraction_grid(
                    scene["path"], shape=(image.size[1], image.size[0])) or {}
            except Exception:
                water = {}
            crops = [crop for crop, _, _ in windows]
            with torch.inference_mode():
                for start in range(0, len(crops), batch):
                    self.status.update(current=f"Scene {scene['id']}: tiles {start + 1}–{min(start + batch, len(crops))} / {len(crops)}")
                    chunk = crops[start:start + batch]
                    stacked = torch.stack(
                        [self.preprocess(c) for c in chunk]).to(self.device)
                    value = self.model.encode_image(stacked)
                    value = (value / value.norm(dim=-1, keepdim=True)).cpu().numpy()
                    for offset, vector in enumerate(value):
                        index = start + offset
                        _, row, col = windows[index]
                        rows.append((scene["id"], index, row, col,
                                     float(water.get((row, col), 0.0)),
                                     vector.astype("float32").tobytes(),
                                     stamp[scene["id"]]))
            self.status.update(current=f"tiling scene {scene['id']}")
        with closing(sqlite3.connect(path)) as cache:
            with cache:
                cache.executemany(
                    "insert or replace into tile_features values(?,?,?,?,?,?,?)", rows
                )
            total = cache.execute("select count(*) from tile_features").fetchone()[0]
        self.status.update(
            tile_vectors=total, tile_px=TILE_PX, tiles_encoded=len(rows),
            tiles_reused=total - len(rows),
        )
        return total

    def class_vectors(self):
        """One unit vector per land-cover group, from the same prompts the
        change typer uses. Built once, then reused."""
        cached = getattr(self, "_cover_vectors", None)
        if cached is not None:
            return cached

        import open_clip
        import torch

        from app.change_typing import CLASS_PROMPTS, PROMPT_TEMPLATE

        self.load()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        names, vectors = list(CLASS_PROMPTS), []
        with torch.inference_mode():
            for name in names:
                prompts = [PROMPT_TEMPLATE.format(p) for p in CLASS_PROMPTS[name]]
                encoded = self.model.encode_text(
                    tokenizer(prompts).to(self.device))
                encoded = encoded / encoded.norm(dim=-1, keepdim=True)
                mean = encoded.mean(dim=0)
                vectors.append((mean / mean.norm()).cpu().numpy())
        self._cover_vectors = (names, np.stack(vectors).astype("float32"))
        return self._cover_vectors

    def scene_labels(self, scene_id, top=3):
        """What each 224 px window of a scene looks like.

        Scored against stored tile vectors, so this costs a matmul and no new
        image pass. These are zero-shot prompt matches, not validated
        land-cover classes - the caller must not print them as ground truth.
        """
        names, matrix = self.class_vectors()
        with closing(sqlite3.connect(self.data / "semantic_cache.sqlite3")) as cache:
            try:
                rows = cache.execute(
                    "select tile_index,row,col,water_fraction,vector from"
                    " tile_features where scene_id=? order by tile_index",
                    (int(scene_id),),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            granularity = f"{TILE_PX} px windows"
            if not rows:
                # A scene no larger than one window has only its scene vector;
                # a duplicate capture shares its representative's vector.
                canonical = next((s["id"] for g in getattr(self, "groups", []) or []
                                  for s in g.get("scenes", [])
                                  if int(scene_id) in s.get("duplicate_scene_ids", [])),
                                 int(scene_id))
                try:
                    hit = cache.execute("select vector from scene_features where scene_id=?",
                                        (canonical,)).fetchone()
                except sqlite3.OperationalError:
                    hit = None
                rows = [(0, 0, 0, 0.0, hit[0])] if hit else []
                granularity = "whole scene"
        if not rows:
            return {"scene_id": int(scene_id), "windows": [],
                    "note": "this scene is not in the semantic index: it was withheld at"
                            " screening, or the local index has not been built yet"}

        vectors = np.vstack([np.frombuffer(r[4], dtype="float32") for r in rows])
        scores = vectors @ matrix.T
        windows, tally = [], {name: 0 for name in names}
        for (tile_index, row, col, water, _), score in zip(rows, scores):
            order = np.argsort(score)[::-1]
            best = names[int(order[0])]
            tally[best] += 1
            windows.append({
                "tile_index": tile_index, "row": row, "col": col,
                "water_fraction": round(float(water), 4),
                "labels": [{"class": names[int(i)], "score": round(float(score[i]), 4)}
                           for i in order[:top]],
            })
        total = len(windows)
        return {
            "scene_id": int(scene_id),
            "granularity": granularity,
            "window_px": TILE_PX,
            "window_km": round(TILE_PX * 10 / 1000, 2),
            "windows": windows,
            "cover": {name: round(count / total, 4)
                      for name, count in sorted(tally.items(), key=lambda kv: -kv[1])},
            "encoder": "RemoteCLIP ViT-B-32 zero-shot against fixed prompts",
            "caveat": "Prompt matches, not validated land-cover labels."
                      " No ground-truth check has been run against these.",
        }

    def rank_vectors(self, rows, query_vector, limit=200, near_water=False,
                     water_min=None, cover_weight=COVER_WEIGHT):
        """One exact archive index; postfilter without losing filtered top-k hits."""
        import faiss

        path = self.data / "semantic_cache.sqlite3"
        archive = self.snapshot()
        version = (
            path.stat().st_mtime_ns,
            tuple((r["id"], r["sha256"], r["imported_at"]) for r in archive),
        )
        with self.guard:
            if getattr(self, "_rank_version", None) != version:
                with closing(sqlite3.connect(path)) as cache:
                    vectors = dict(
                        cache.execute("select scene_id,vector from scene_features")
                    )
                    try:
                        tiles = cache.execute(
                            "select scene_id,vector,row,col,water_fraction"
                            " from tile_features"
                        ).fetchall()
                    except sqlite3.OperationalError:
                        tiles = []
                indexed = [r for r in archive if r["id"] in vectors]
                if not indexed:
                    return []
                # Rank over tile vectors when they exist: a query about a runway
                # should match the window holding the runway, not an average of
                # 10 km of mostly-unrelated ground.
                by_scene = {r["id"]: r for r in indexed}
                rows_for_matrix, blobs, cells = [], [], []
                for scene_id, blob, row, col, water in tiles:
                    if scene_id in by_scene:
                        rows_for_matrix.append(by_scene[scene_id])
                        blobs.append(blob)
                        cells.append((scene_id, row, col, water))
                # A scene no larger than one window has no tile rows. Without
                # this, one large scene in the archive hid every small one.
                if blobs:
                    tiled = {cell[0] for cell in cells}
                    for r in indexed:
                        if r["id"] not in tiled:
                            rows_for_matrix.append(r)
                            blobs.append(vectors[r["id"]])
                            cells.append((r["id"], 0, 0, 0.0))
                granularity = "tile"
                if not blobs:
                    granularity = "scene"
                    rows_for_matrix = indexed
                    blobs = [vectors[r["id"]] for r in indexed]
                self._tile_matrix = None
                if granularity == "tile":
                    # Pure max over 1888 windows loses to whichever unrelated
                    # window wins on noise: it halved top-1 on the full archive
                    # while raising top-5. Mean of the best TILE_TOP_K windows
                    # keeps the recall gain without that. See
                    # reality_check/tile_aggregation.py.
                    # ponytail: exact matmul, not FAISS. 1888x512 is microseconds;
                    # revisit if the archive reaches six figures of tiles.
                    self._tile_matrix = np.ascontiguousarray(
                        [np.frombuffer(b, dtype="float32") for b in blobs])
                    self._tile_scene_ids = np.array(
                        [r["id"] for r in rows_for_matrix], dtype="int64")
                    self._tile_cells = cells
                    names, cover = self.class_vectors()
                    self._cover_names = names
                    self._tile_cover = _softmax(self._tile_matrix @ cover.T)
                matrix = np.ascontiguousarray(
                    [np.frombuffer(b, dtype="float32") for b in blobs]
                )
                index = faiss.IndexFlatIP(matrix.shape[1])
                index.add(matrix)
                self._rank_version = version
                self._rank_index = index
                self._rank_rows = rows_for_matrix
                self._rank_granularity = granularity
            index, indexed = self._rank_index, self._rank_rows
            tile_matrix = getattr(self, "_tile_matrix", None)
            tile_scene_ids = getattr(self, "_tile_scene_ids", None)
            tile_cells = getattr(self, "_tile_cells", None)
            tile_cover = getattr(self, "_tile_cover", None)
        allowed = {r["id"]: r for r in rows}
        if tile_matrix is not None:
            query = np.ascontiguousarray(query_vector, dtype="float32").reshape(-1)
            similarity = tile_matrix @ query
            if tile_cover is not None and cover_weight:
                # Nudge windows whose land cover matches what the query asks
                # for. Small on purpose: at 0.20 this rule takes over and
                # ranking collapses.
                _, cover = self.class_vectors()
                similarity = similarity + cover_weight * (
                    tile_cover @ _softmax(cover @ query))
            keep = np.ones(len(similarity), dtype=bool)
            if near_water and tile_cells is not None:
                keep = np.array(near_water_mask(tile_cells, water_min), dtype=bool)
            best = {}
            for scene_id in np.unique(tile_scene_ids[keep]):
                scene_id = int(scene_id)
                if scene_id not in allowed:
                    continue
                scores = similarity[(tile_scene_ids == scene_id) & keep]
                if not len(scores):
                    continue
                top = np.sort(scores)[-TILE_TOP_K:]
                best[scene_id] = (dict(allowed[scene_id]), float(top.mean()))
            return sorted(best.values(), key=lambda pair: -pair[1])[:limit]
        query = np.ascontiguousarray(query_vector, dtype="float32").reshape(1, -1)
        take = min(max(1, limit), len(indexed))
        while True:
            scores, ids = index.search(query, take)
            # With tile vectors one scene can match several times; keep its best
            # window and report the scene once.
            best = {}
            for i, score in zip(ids[0], scores[0]):
                if i < 0:
                    continue
                scene_id = indexed[int(i)]["id"]
                if scene_id not in allowed:
                    continue
                if scene_id not in best or score > best[scene_id][1]:
                    best[scene_id] = (dict(allowed[scene_id]), float(score))
            matches = sorted(best.values(), key=lambda pair: -pair[1])
            if len(matches) >= limit or take >= len(indexed):
                return matches[:limit]
            take = min(len(indexed), take * 2)

    def expand_temporal_results(self, direct, active_rows):
        """Expand only built temporal groups, joined to the filtered active archive.

        Only direct structural hits seed expansion; never recursively expand
        added members or use cross-location similar-site groups.
        """
        available = {r["id"]: r for r in active_rows}
        seeds = {r["id"] for r in direct if r.get("structural_match")}
        output = [
            dict(
                r,
                retrieval_source=(
                    "direct_structural_match"
                    if r.get("structural_match")
                    else "direct_visual_similarity"
                ),
            )
            for r in direct
        ]
        seen = {r["id"] for r in output}
        with self.guard:
            groups = list(self.groups) if self.status.get("state") == "ready" else []
        for group in groups:
            members = {r["id"] for r in group["scenes"]}
            anchors = sorted(members & seeds)
            if not anchors:
                continue
            for scene_id in sorted(members):
                if scene_id in seen or scene_id not in available:
                    continue
                row = dict(available[scene_id])
                if not Path(row["path"]).is_file():
                    continue
                row.update(
                    match_score=None,
                    score_type="Same-location timeline member — inspect changes",
                    structural_match=False,
                    structural_evidence=None,
                    retrieval_source="temporal_cluster",
                    cluster_key=group["key"],
                    matched_via_scene_ids=anchors,
                    search_mode="uploaded-image",
                )
                output.append(row)
                seen.add(scene_id)
        return output

    def result(self, limit=100, mode="temporal"):
        self.ensure()
        with self.guard:
            return (self.similar_sites if mode == "similar" else self.groups)[
                : max(1, min(limit, 500))
            ]
