"""خادم الفيديو: يولّد مقاطع قصيرة ويربطها ويمدّدها. تشغيل: uvicorn main:app --port 8000"""
import base64, json, math, os, subprocess, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from providers import get_provider, W, H

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
MAX_TOTAL = int(os.environ.get("MAX_TOTAL_SECONDS", 600))

app = FastAPI(title="AI Studio Video Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=OUT), name="outputs")

pool = ThreadPoolExecutor(max_workers=1)  # مهمة واحدة في كل مرة (GPU واحد)
jobs: dict = {}
lock = threading.Lock()
_provider = None


def provider():
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def normalize(src: Path, dst: Path):
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p")
    ff("-i", str(src), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", str(dst))


def last_frame(video: Path, dst: Path):
    ff("-sseof", "-0.2", "-i", str(video), "-frames:v", "1", "-update", "1", str(dst))


def concat(clips, dst: Path):
    lst = dst.parent / "list.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264",
       "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", str(dst))


def save(job):
    (OUT / job["id"] / "job.json").write_text(json.dumps(job, ensure_ascii=False))


def run_job(job, prompt, n_clips, clip_sec, seed, image: Path | None, base: Path | None):
    d = OUT / job["id"]
    try:
        job["status"] = "running"
        clips = [base] if base else []
        current = base
        for i in range(n_clips):
            raw, norm = d / f"raw{i}.mp4", d / f"clip{i}.mp4"
            if current is not None:
                frame = d / f"frame{i}.png"
                last_frame(current, frame)
                src_img = frame
            else:
                src_img = image
            provider().generate(prompt, clip_sec, raw, image=src_img, seed=seed)
            normalize(raw, norm)
            clips.append(norm)
            current = norm
            job["clips_done"] = i + 1
            job["progress"] = int((i + 1) / n_clips * 95)
            save(job)
        final = d / "final.mp4"
        concat(clips, final)
        job.update(status="done", progress=100, url=f"/outputs/{job['id']}/final.mp4")
    except Exception as e:  # noqa: BLE001
        job.update(status="error", error=str(e)[:500])
    save(job)


class NewJob(BaseModel):
    mode: str = "text"            # text | image
    prompt: str
    image_b64: str | None = None
    total_seconds: int = 10
    clip_seconds: int = 5
    seed: int = 0
    character_desc: str = ""


class Extend(BaseModel):
    prompt: str = ""
    extra_seconds: int = 10
    seed: int = 0
    character_desc: str = ""


def make_job(prompt, total, clip, seed, image, base, parent=None):
    if total < clip or total > MAX_TOTAL:
        raise HTTPException(400, f"المدة يجب أن تكون بين {clip} و{MAX_TOTAL} ثانية")
    jid = uuid.uuid4().hex[:10]
    (OUT / jid).mkdir()
    n = math.ceil(total / clip)
    job = dict(id=jid, status="queued", progress=0, clips_done=0, clips_total=n,
               url=None, error=None, prompt=prompt, parent=parent)
    with lock:
        jobs[jid] = job
    save(job)
    pool.submit(run_job, job, prompt, n, clip, seed, image, base)
    return job


@app.get("/")
def index():
    f = ROOT.parent / "index.html"
    return FileResponse(f) if f.exists() else {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True, "provider": os.environ.get("VIDEO_PROVIDER", "mock"), "max_seconds": MAX_TOTAL}


@app.post("/api/video/jobs")
def create(req: NewJob):
    image = None
    if req.mode == "image":
        if not req.image_b64:
            raise HTTPException(400, "أرسل صورة لوضع صورة إلى فيديو")
        raw = req.image_b64.split(",")[-1]
        tmp = OUT / f"up_{uuid.uuid4().hex[:8]}.png"
        tmp.write_bytes(base64.b64decode(raw))
        image = tmp
    prompt = f"{req.character_desc}. {req.prompt}".strip(". ") if req.character_desc else req.prompt
    return make_job(prompt, req.total_seconds, max(2, min(req.clip_seconds, 10)), req.seed, image, None)


@app.post("/api/video/jobs/{jid}/extend")
def extend(jid: str, req: Extend):
    parent = jobs.get(jid)
    if not parent or parent["status"] != "done":
        raise HTTPException(400, "الفيديو الأصلي غير جاهز")
    base = OUT / jid / "final.mp4"
    prompt = req.prompt or parent["prompt"]
    if req.character_desc:
        prompt = f"{req.character_desc}. {prompt}"
    return make_job(prompt, req.extra_seconds, 5, req.seed, None, base, parent=jid)


@app.get("/api/video/jobs/{jid}")
def status(jid: str):
    job = jobs.get(jid)
    if not job:
        f = OUT / jid / "job.json"
        if f.exists():
            return json.loads(f.read_text())
        raise HTTPException(404, "غير موجود")
    return job
