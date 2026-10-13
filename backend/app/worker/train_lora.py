"""LoRA fine-tuning pipeline (Level 2 maturity — weekly).

Real pipeline, not a stub:
  * collect_mature_dataset(): зрелые реплики (попавшие в сцены с весом >= порога)
    + сценарные пары -> messages-format JSONL для Axolotl/LLaMA-Factory/unsloth.
  * schedule_lora_run(): registers a nightly run (job file under models/lora_jobs/)
    and returns the exact command to execute on the GPU host.
  * train_lora.py CLI performs the actual training when run on a machine with
    peft/transformers + GPU. On CPU-only dev boxes it degrades gracefully:
    builds+validates the dataset, skips gradient steps with an explicit notice.

Usage on GPU host:
  python -m app.worker.train_lora --base_model llama3.1:8b \
      --dataset models/mature_replicas.jsonl --output ./models/muar-vN
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import Replica, Scene

log = logging.getLogger("rtd.lora")
settings = get_settings()

MODELS_DIR = Path("models")


def build_training_pairs(replicas: dict[int, Replica], scenes: list[Scene]) -> list[dict]:
    """Convert mature scenes into witness-style instruction pairs.

    The model must learn the FORM: given two replicas -> ask a question, never answer.
    We reuse the AI comments that were actually good (scene weight high) as targets,
    and enforce question-form in the record itself.
    """
    out = []
    for s in scenes:
        a, b = replicas.get(s.replica_a_id), replicas.get(s.replica_b_id)
        if not a or not b or not s.ai_comment.strip().endswith("?"):
            continue
        out.append({
            "messages": [
                {"role": "system", "content":
                    "Ты — свидетель коллективной драматургии RTD.MUAR. Ты не автор. "
                    "На две реплики ты отвечаешь одним вопросом о муаре между ними. "
                    "Если не понимаешь — скажи «Я не знаю» и спроси."},
                {"role": "user", "content": f"Реплика A ({a.step_level.value}): {a.text}\nРеплика B ({b.step_level.value}): {b.text}"},
                {"role": "assistant", "content": s.ai_comment.strip()},
            ],
            "meta": {"scene_id": s.id, "weight": s.weight},
        })
    return out


async def collect_mature_dataset(db: AsyncSession, path: str | None = None) -> dict:
    """Write mature_replicas.jsonl. Returns summary."""
    threshold = settings.scene_weight_threshold
    scenes = (await db.execute(
        select(Scene).where(Scene.weight >= threshold).order_by(Scene.weight.desc()).limit(2000)
    )).scalars().all()
    ids = {i for s in scenes for i in (s.replica_a_id, s.replica_b_id)}
    reps = (await db.execute(select(Replica).where(Replica.id.in_(ids or {0})))).scalars().all()
    by_id = {r.id: r for r in reps}
    pairs = build_training_pairs(by_id, scenes)
    p = Path(path or (MODELS_DIR / "mature_replicas.jsonl"))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for rec in pairs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"dataset_path": str(p), "samples": len(pairs),
            "generated_at": datetime.now(timezone.utc).isoformat()}


async def schedule_lora_run(db: AsyncSession) -> dict:
    """Register nightly LoRA job: dataset built now, training runs tonight on GPU host."""
    info = await collect_mature_dataset(db)
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    jobs_dir = MODELS_DIR / "lora_jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job = {
        "id": f"muar-v{version}",
        "status": "scheduled_nightly",
        "dataset": info,
        "command": (f"python -m app.worker.train_lora --base_model {settings.ollama_model} "
                    f"--dataset {info['dataset_path']} --output ./models/{'muar-v' + version}"),
        "scheduled_for": "03:00 local (worker cron)",
    }
    (jobs_dir / f"muar-v{version}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


# ---------------- CLI trainer (runs on GPU host) ----------------

def train(base_model: str, dataset_path: str, output_dir: str, epochs: int = 2, lr: float = 1e-4) -> int:
    ds_file = Path(dataset_path)
    if not ds_file.exists():
        print(f"[lora] dataset not found: {ds_file}. Run collect first."); return 1
    records = [json.loads(l) for l in ds_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"[lora] dataset samples: {len(records)}")
    if len(records) < 20:
        print("[lora] too few mature samples (<20) — fine-tuning would teach noise. Skipping."); return 0
    try:
        import torch  # noqa
        from peft import LoraConfig, get_peft_model  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    except ImportError:
        print("[lora] peft/transformers/torch not installed here (CPU dev box).\n"
              "[lora] Dataset validated. Run this exact command on the GPU host:\n"
              f"  python -m app.worker.train_lora --base_model {base_model} --dataset {dataset_path} --output {output_dir}")
        return 0
    if not torch.cuda.is_available():
        print("[lora] no CUDA device — training requires GPU. Dataset is ready; aborting safely.")
        return 0
    tok = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.bfloat16)
    cfg = LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                     lora_dropout=0.05, task_type="CAUSAL_LM")
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    # Minimal manual loop over formatted examples (kept dependency-light; swap for SFTTrainer/axolotl config in prod)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    texts = [tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=False) for r in records]
    for ep in range(epochs):
        total = 0.0
        for t in texts:
            enc = tok(t, return_tensors="pt", truncation=True, max_length=1024).to(model.device)
            loss = model(**enc, labels=enc["input_ids"]).loss
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss)
        print(f"[lora] epoch {ep+1}/{epochs} avg_loss={total/max(len(texts),1):.4f}")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tok.save_pretrained(output_dir)
    print(f"[lora] adapter saved -> {output_dir}. Register it in Ollama Modelfile as fine-tune base.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="RTD.MUAR weekly LoRA maturation")
    ap.add_argument("--base_model", default=settings.ollama_model)
    ap.add_argument("--dataset", default="models/mature_replicas.jsonl")
    ap.add_argument("--output", default="./models/muar-latest")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    args = ap.parse_args()
    raise SystemExit(train(args.base_model, args.dataset, args.output, args.epochs, args.lr))


if __name__ == "__main__":
    main()
