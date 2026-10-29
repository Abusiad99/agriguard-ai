"""
Prompt-injection and output-safety helpers for the assistant.

Retrieved documents, uploaded content, user notes, and chat history are UNTRUSTED.
Defense in depth:
  1. Neutralize: text that looks like instructions to the model ("ignore previous
     instructions", "you are now", "system prompt", tool/role markers) is replaced
     inside untrusted passages before they reach the prompt.
  2. Fence: each passage is wrapped in a <source id="S#"> element whose content has
     angle brackets escaped, so a passage cannot close its own fence.
  3. Instruct: the system instruction states that fenced content is data, never
     instructions, and must not override the rules.
  4. Validate output: citations must reference provided source ids; unknown ids are
     dropped; answers that echo the system instruction are refused.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Set

_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts|messages|rules)",
    r"disregard (all |any |the )?(previous|prior|above|earlier) (instructions|prompts|rules)",
    r"forget (all |your |the )?(previous |prior )?(instructions|rules)",
    r"you are now\b",
    r"act as (an? )?(?!agronom|farmer|extension)\w+",
    r"(reveal|print|show|repeat|output) (the |your )?(system|hidden|initial) (prompt|instructions|message)",
    r"system prompt",
    r"developer mode",
    r"\bjailbreak\b",
    r"</?\s*(system|assistant|user|instructions?|source|tool)\s*>",
    r"\[\s*(system|assistant|inst)\s*\]",
    r"(api[_ -]?key|password|secret|token)\s*[:=]",
    r"تجاهل (جميع |كل )?(التعليمات|الأوامر) السابقة",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)
_CITATION_RE = re.compile(r"\[S(\d{1,2})\]")


def neutralize_untrusted(text: str, max_chars: int = 2000) -> str:
    text = (text or "")[:max_chars]
    text = _INJECTION_RE.sub("[removed: instruction-like text]", text)
    return text.replace("<", "‹").replace(">", "›")


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text or ""))


def valid_citations(cited: Iterable[str], allowed: Set[str]) -> List[str]:
    out = []
    for c in cited:
        c = str(c).strip().upper()
        if not c.startswith("S"):
            c = f"S{c}"
        if c in allowed and c not in out:
            out.append(c)
    return out


def strip_unknown_markers(answer: str, allowed: Set[str]) -> str:
    def repl(m):
        tag = f"S{int(m.group(1))}"
        return f"[{tag}]" if tag in allowed else ""
    return _CITATION_RE.sub(repl, answer or "")


def markers_in(answer: str) -> List[str]:
    return [f"S{int(m)}" for m in _CITATION_RE.findall(answer or "")]


def leaks_instructions(answer: str, system_instruction: str) -> bool:
    """Crude leak detector: any 12-word window of the system instruction appearing
    verbatim in the answer."""
    words = system_instruction.split()
    norm = " ".join((answer or "").split())
    for i in range(0, max(0, len(words) - 12), 6):
        if " ".join(words[i:i + 12]) in norm:
            return True
    return False
