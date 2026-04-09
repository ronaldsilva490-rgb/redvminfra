from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISCOVERED = ROOT / "data" / "discovered_models.json"
OUTPUT = ROOT / "candidate_models.json"


EXCLUDE_PATTERNS = [
    "allam",
    "whisper",
    "tts",
    "transcribe",
    "realtime",
    "embed",
    "moderation",
    "ocr",
    "pixtral",
    "voxtral",
    "vibe-cli",
    "prompt-guard",
    "safeguard",
    "orpheus",
    "codestral",
    "leanstral",
    "creative",
]


PRIORITY = {
    "groq": [
        "qwen/qwen3-32b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.3-70b-versatile",
        "groq/compound-mini",
        "groq/compound",
        "moonshotai/kimi-k2-instruct",
        "moonshotai/kimi-k2-instruct-0905",
        "llama-3.1-8b-instant",
    ],
    "mistral": [
        "mistral-small-latest",
        "mistral-small-2603",
        "mistral-medium-latest",
        "mistral-medium-2508",
        "mistral-large-latest",
        "mistral-large-2512",
        "magistral-small-latest",
        "magistral-medium-latest",
        "ministral-3b-latest",
        "ministral-8b-latest",
        "ministral-14b-latest",
        "devstral-latest",
        "devstral-medium-latest",
        "devstral-small-2507",
        "open-mistral-nemo",
        "open-mistral-nemo-2407",
    ],
}


def should_exclude(model_id: str) -> tuple[bool, str]:
    lowered = model_id.lower()
    for pattern in EXCLUDE_PATTERNS:
        if pattern in lowered:
            return True, pattern
    return False, ""


def rank_models(provider: str, models: list[str]) -> list[str]:
    priority = PRIORITY.get(provider, [])
    priority_map = {model: index for index, model in enumerate(priority)}
    return sorted(
        models,
        key=lambda model: (
            0 if model in priority_map else 1,
            priority_map.get(model, 10_000),
            model.lower(),
        ),
    )


def main() -> int:
    discovered = json.loads(DISCOVERED.read_text(encoding="utf-8"))
    output: dict[str, object] = {
        "generated_from": str(DISCOVERED.as_posix()),
        "providers": {},
        "benchmark_round_1": [],
    }
    for provider, models in discovered.items():
        included = []
        excluded = []
        for model in models:
            skip, reason = should_exclude(model)
            if skip:
                excluded.append({"id": model, "reason": reason})
            else:
                included.append(model)
        ordered = rank_models(provider, included)
        output["providers"][provider] = {
            "included": ordered,
            "excluded": excluded,
            "priority_top_10": ordered[:10],
        }
        for item in ordered[:10]:
            suffix = " (GROQ)" if provider == "groq" else " (MISTRAL)"
            output["benchmark_round_1"].append(
                {
                    "provider": provider,
                    "model": item,
                    "display_name": item + suffix,
                }
            )
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
