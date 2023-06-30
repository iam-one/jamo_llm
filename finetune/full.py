from torch.utils.data import DataLoader
from pathlib import Path
import torch
import sys
import argparse

wd = Path(__file__).parent.parent.resolve()
sys.path.append(str(wd))

from dataset import PromptDataset
from sophia import SophiaG
from jamo import Tokenizer
import utils
from jamo.trainer import Trainer


class FullTrainer(Trainer):
    def __init__(self, model_size:str, learning_rate: float, batch_size: int, corpus_path: str, checkpoint_dir: str, tokenizer_path: str,
                 max_iters: int, warmup_iters: int, save_interval: int, eval_interval: int, gradient_accumulate: int, with_lr_scheduler: bool):
        Trainer.__init__(self, learning_rate, batch_size, corpus_path, checkpoint_dir, tokenizer_path, save_interval, eval_interval, gradient_accumulate)


        model_path = Path("../tmp/checkpoint")
        self.model = utils.load_model(model_path, model_size=model_size, device="cuda")
        self.optimizer = SophiaG(self.model.parameters(), lr=learning_rate, betas=(0.965, 0.99), rho=0.03, weight_decay=0.2)

        # self.tokenizer: Tokenizer = Tokenizer(self.tokenizer_path)
        self.tokenizer = None
        self.train_loader: DataLoader = self.create_dataloader(tokenizer=self.tokenizer, block_size=self.model.config.block_size)

        self.max_iters = max_iters
        self.warmup_iters = warmup_iters
        self.with_lr_scheduler = with_lr_scheduler

    def get_lr(self, iteration: int):
        lr = self.learning_rate * iteration / self.warmup_iters if self.warmup_iters > iteration else self.learning_rate
        return lr

    def create_dataloader(self, tokenizer, block_size: int):
        g = torch.Generator()
        g.manual_seed(1231928)
        # dataset = PromptDataset(str(self.corpus_path), tokenizer, block_size)
        train_dataset = PromptDataset(cache_dir="../tmp/cache/sft-cache.hdf5")
        eval_dataset = PromptDataset(cache_dir="../tmp/cache/stf-cache.hdf5", mode="eval")
        train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True, drop_last=True, generator=g)
        eval_loader = DataLoader(eval_dataset, batch_size=self.batch_size, shuffle=False, drop_last=True)
        self.logger.info("Finishing Loading the DataLoader")

        return train_loader
    
    @torch.no_grad()
    def eval(self, iteration):
        losses = []
        for _, (x, y) in enumerate(self.eval_loader):
            logits = self.model(x)
            loss = torch.nn.functional.cross_entropy(logits.view(-1, logits.shape[-1]), y.view(-1), ignore_index=-1)
            losses.append(loss.item())

        min_loss = sum(losses) / len(losses)
        self.writer.add_scalar("Loss/eval", min_loss, iteration)
        self.logger.info(f"Iter {iteration}: Eval Loss = {min_loss}")


if __name__ == "__main__":
    torch.set_float32_matmul_precision("high")

    parser = argparse.ArgumentParser(description='Pretraining your own custom LLM 🚀!!!')

    parser.add_argument("--model_size", type=str, default="small")
    parser.add_argument("--learning_rate", type=float, default=5e-4)
    parser.add_argument("--batch_size", type=int, default=60)
    parser.add_argument("--max_iters", type=int, default=200)
    parser.add_argument("--warmup_iters", type=int, default=40)
    parser.add_argument("--save_interval", type=int, default=50)
    parser.add_argument("--eval_interval", type=int, default=50)
    parser.add_argument("--gradient_accumulate", type=int, default=6)
    parser.add_argument("--checkpoint_dir", type=str, default="../tmp/finetuned")
    parser.add_argument("--corpus_path", type=str, default="../tmp/ko_alpaca_data.json")
    parser.add_argument("--tokenizer_path", type=str, default="hg_tokenizer")
    parser.add_argument("--with_lr_scheduler", action="store_true")

    args = parser.parse_args()

    trainer = FullTrainer(
        model_size=args.model_size,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        max_iters=args.max_iters,
        warmup_iters=args.warmup_iters,
        corpus_path=args.corpus_path,
        checkpoint_dir=args.checkpoint_dir,
        tokenizer_path=args.tokenizer_path,
        save_interval=args.save_interval,
        eval_interval=args.eval_interval,
        gradient_accumulate=args.gradient_accumulate,
        with_lr_scheduler=args.with_lr_scheduler
    )

    trainer.train()
