# core/options.py
from dataclasses import dataclass
from config import DEFAULT_REGION

@dataclass
class AnalysisOptions:
    region: str = DEFAULT_REGION
    lang: str = "ru"
    fee: float = 5.0
    recursive: bool = False
    max_depth: int = 12
    no_fallback: bool = False
    no_history: bool = False
    max_requests: int = 500
    workers: int = 4
    no_heartbeat: bool = False
    verbose: bool = False
    explain: bool = False
    explain_tree: bool = False
    ignore_missing: bool = False
    exclude: str = ""
    show_ids: bool = False

    @classmethod
    def from_args(cls, args) -> "AnalysisOptions":
        return cls(
            region=args.region, lang=args.lang, fee=args.fee,
            recursive=args.recursive, max_depth=args.max_depth,
            no_fallback=args.no_fallback, no_history=args.no_history,
            max_requests=args.max_requests, workers=args.workers,
            no_heartbeat=args.no_heartbeat, verbose=args.verbose,
            explain=args.explain, explain_tree=args.explain_tree,
            ignore_missing=args.ignore_missing, exclude=args.exclude,
            show_ids=args.show_ids,
        )

    @classmethod
    def menu_defaults(cls) -> "AnalysisOptions":
        return cls(
            recursive=True,
            no_history=True,
            no_heartbeat=True,
            max_requests=2000,
        )