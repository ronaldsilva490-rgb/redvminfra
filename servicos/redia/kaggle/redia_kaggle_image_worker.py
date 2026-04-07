#!/usr/bin/env python3
"""
REDIA Kaggle Image Worker.

Run in Kaggle after installing:
  pip install -U diffusers transformers accelerate safetensors pillow requests

This worker is intentionally pull-based. Kaggle does not need a public endpoint.
"""

import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
from typing import Any

import requests


BLOCKED_PATTERNS = [
    r"\b(minor|child|teen|schoolgirl|underage|young-looking|crianca|infantil|adolescente|novinha|novinho)\b",
    r"\b(deepfake|nudify|celebrity|real person|pessoa real|famosa|famoso)\b",
    r"\b(non-consensual|rape|coercion|forced|estupro|forcad[oa]|sem consentimento)\b",
    r"\b(genitals|explicit sex|porn|porno|sexo explicito)\b",
]


def blocked(text: str) -> bool:
    folded = (text or "").lower()
    return any(re.search(pattern, folded, flags=re.I) for pattern in BLOCKED_PATTERNS)


def post_json(path: str, payload: dict[str, Any], token: str, base_url: str, timeout: int = 60) -> dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def load_pipeline(model_id: str, device: str):
    import torch
    from diffusers import AutoPipelineForText2Image, AutoencoderKL

    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    vae = None
    if "sdxl" in model_id.lower():
        try:
            vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
        except Exception as exc:
            print(f"[{device}] fixed VAE fallback: {exc!r}", flush=True)
    pipe = AutoPipelineForText2Image.from_pretrained(
        model_id,
        torch_dtype=dtype,
        variant="fp16" if dtype == torch.float16 else None,
        use_safetensors=True,
        vae=vae,
    )
    pipe = pipe.to(device)
    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass
    try:
        pipe.enable_vae_slicing()
    except Exception:
        pass
    return pipe


def generate(pipe, job: dict[str, Any], device: str) -> tuple[str, int, int]:
    import torch

    prompt = str(job.get("safe_prompt") or "").strip()
    negative_prompt = str(job.get("negative_prompt") or "").strip()
    if not prompt:
        raise ValueError("job has empty prompt")
    if blocked(prompt):
        raise ValueError("worker policy blocked prompt")

    width = int(job.get("width") or 768)
    height = int(job.get("height") or 768)
    steps = int(job.get("steps") or 4)
    cfg = float(job.get("cfg") or 1.5)
    if "turbo" in str(os.environ.get("REDIA_MODEL_ID", "")).lower():
        cfg = 0.0
    seed = int(time.time() * 1000) % 2_147_483_647
    generator = torch.Generator(device=device).manual_seed(seed) if device.startswith("cuda") else torch.Generator().manual_seed(seed)

    started = time.time()
    image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt or None,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=cfg,
        generator=generator,
    ).images[0]
    elapsed_ms = int((time.time() - started) * 1000)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    return encoded, elapsed_ms, seed


def run_worker(worker_name: str, device: str, base_url: str, token: str, model_id: str, poll_seconds: float):
    print(f"[{worker_name}] loading {model_id} on {device}", flush=True)
    pipe = load_pipeline(model_id, device)
    print(f"[{worker_name}] ready", flush=True)
    while True:
        try:
            payload = post_json("/api/image/worker/claim", {"worker_id": worker_name}, token, base_url, timeout=30)
            job = payload.get("job")
            if not job:
                time.sleep(poll_seconds)
                continue
            job_id = job.get("id")
            print(f"[{worker_name}] claimed job #{job_id}", flush=True)
            post_json("/api/image/worker/generating", {"worker_id": worker_name, "job_id": job_id}, token, base_url, timeout=30)
            try:
                image_base64, generation_ms, seed = generate(pipe, job, device)
                post_json(
                    "/api/image/worker/result",
                    {
                        "ok": True,
                        "worker_id": worker_name,
                        "job_id": job_id,
                        "mime_type": "image/png",
                        "image_base64": image_base64,
                        "generation_ms": generation_ms,
                        "seed": seed,
                    },
                    token,
                    base_url,
                    timeout=120,
                )
                print(f"[{worker_name}] completed job #{job_id} in {generation_ms}ms", flush=True)
            except Exception as exc:
                post_json(
                    "/api/image/worker/result",
                    {"ok": False, "worker_id": worker_name, "job_id": job_id, "error": repr(exc)},
                    token,
                    base_url,
                    timeout=60,
                )
                print(f"[{worker_name}] failed job #{job_id}: {exc!r}", flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[{worker_name}] loop error: {exc!r}", flush=True)
            time.sleep(max(5, poll_seconds))


def spawn_dual(args):
    procs = []
    for index in [0, 1]:
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(index)
        env["REDIA_WORKER_TOKEN"] = args.worker_token
        cmd = [
            sys.executable,
            __file__,
            "--worker-name",
            f"{args.worker_name}-{index}",
            "--device",
            "cuda:0",
            "--base-url",
            args.base_url,
            "--model-id",
            args.model_id,
            "--poll-seconds",
            str(args.poll_seconds),
        ]
        procs.append(subprocess.Popen(cmd, env=env))
    try:
        while any(proc.poll() is None for proc in procs):
            time.sleep(2)
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("REDIA_BASE_URL", "http://redsystems2.ddns.net:3099"))
    parser.add_argument("--worker-name", default=os.environ.get("REDIA_WORKER_NAME", "kaggle-t4"))
    parser.add_argument("--worker-token", default=os.environ.get("REDIA_WORKER_TOKEN", ""))
    parser.add_argument("--model-id", default=os.environ.get("REDIA_MODEL_ID", "stabilityai/sdxl-turbo"))
    parser.add_argument("--device", default=os.environ.get("REDIA_DEVICE", "cuda:0"))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("REDIA_POLL_SECONDS", "4")))
    parser.add_argument("--dual", action="store_true")
    args = parser.parse_args()

    if not args.worker_token:
        raise SystemExit("REDIA_WORKER_TOKEN is required")
    if args.dual:
        spawn_dual(args)
        return
    run_worker(args.worker_name, args.device, args.base_url, args.worker_token, args.model_id, args.poll_seconds)


if __name__ == "__main__":
    main()
