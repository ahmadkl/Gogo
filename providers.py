"""مزوّدو توليد المقاطع القصيرة. كل مزوّد يملك generate(prompt, seconds, out, image, seed)."""
import json, os, shutil, subprocess
from pathlib import Path

W = int(os.environ.get("VIDEO_WIDTH", 768))
H = int(os.environ.get("VIDEO_HEIGHT", 432))


class MockProvider:
    """يولّد مقاطع اختبار بـ ffmpeg لتجربة التمديد والدمج بدون GPU."""

    def generate(self, prompt, seconds, out, image=None, seed=0):
        n = int(seconds * 24)
        if image:
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"zoompan=z='min(zoom+0.0015,1.3)':d={n}:s={W}x{H}:fps=24")
            cmd = ["ffmpeg", "-y", "-i", str(image), "-vf", vf, "-t", str(seconds),
                   "-pix_fmt", "yuv420p", str(out)]
        else:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
                   f"testsrc2=size={W}x{H}:rate=24:duration={seconds}",
                   "-pix_fmt", "yuv420p", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)


class GradioProvider:
    """يستدعي Hugging Face Space عبر gradio_client."""

    def __init__(self):
        from gradio_client import Client
        self.client = Client(os.environ["HF_SPACE"], hf_token=os.environ.get("HF_TOKEN") or None)
        self.api_name = os.environ.get("HF_API_NAME", "/predict")
        self.map = json.loads(os.environ.get(
            "HF_PARAM_MAP", '{"prompt":"prompt","image":"image","seconds":"duration","seed":"seed"}'))
        self.extra = json.loads(os.environ.get("HF_EXTRA_PARAMS", "{}"))

    def generate(self, prompt, seconds, out, image=None, seed=0):
        from gradio_client import handle_file
        kw = dict(self.extra)
        kw[self.map["prompt"]] = prompt
        if image and self.map.get("image"):
            kw[self.map["image"]] = handle_file(str(image))
        if self.map.get("seconds"):
            kw[self.map["seconds"]] = seconds
        if self.map.get("seed"):
            kw[self.map["seed"]] = seed
        res = self.client.predict(api_name=self.api_name, **kw)
        path = res[0] if isinstance(res, (list, tuple)) else res
        if isinstance(path, dict):
            path = path.get("video") or path.get("value") or path
        if isinstance(path, dict):
            path = path.get("path")
        shutil.copy(path, out)


def get_provider():
    name = os.environ.get("VIDEO_PROVIDER", "mock")
    return GradioProvider() if name == "gradio" else MockProvider()
