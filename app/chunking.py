from dataclasses import dataclass
import re
from .prompts import CONTEXT_SIZE, OUTPUT_TOKENS, SAFETY_TOKENS, map_messages


@dataclass(frozen=True)
class Fragment:
    line: int
    offset: int
    text: str


def continuation(fragment):
    return fragment.offset==0 and bool(re.match(r'^(?:\s+\S|Traceback\b|Caused by:|at\s)',fragment.text))


def pack_next(source, model, memory_for):
    """Pack whole lines; only split a line when it cannot fit alone.

    Input is a bounded lookahead, never the full file. Offsets are Unicode code
    points in the original physical line. Exact templated tokens are returned.
    """
    if not source:
        return [], [], [], ''
    selected = []
    tokens = []
    memory = ''
    limit = CONTEXT_SIZE - OUTPUT_TOKENS - SAFETY_TOKENS
    for i, fragment in enumerate(source):
        candidate = selected + [fragment]
        candidate_memory = memory_for(candidate)
        prepared = model.prepare(map_messages(candidate, candidate_memory))
        if len(prepared) <= limit:
            selected, tokens, memory = candidate, prepared, candidate_memory
            continue
        if selected:
            if continuation(fragment):
                # Move the trailing multiline entry intact when earlier entries
                # can fill this chunk. An entry larger than a whole chunk still
                # splits at physical lines before splitting individual characters.
                group_start = len(selected)-1
                while group_start>0 and continuation(selected[group_start]):
                    group_start -= 1
                if group_start>0:
                    kept = selected[:group_start]
                    kept_memory = memory_for(kept)
                    return kept,model.prepare(map_messages(kept,kept_memory)),source[group_start:],kept_memory
            return selected, tokens, source[i:], memory
        # No line fits: find the largest Unicode-safe prefix that fits.
        lo, hi = 1, len(fragment.text)
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            partial = Fragment(fragment.line, fragment.offset, fragment.text[:mid])
            prepared = model.prepare(map_messages([partial], candidate_memory))
            if len(prepared) <= limit:
                best, tokens = mid, prepared
                lo = mid + 1
            else:
                hi = mid - 1
        if not best:
            raise ValueError('Prompt and memory leave no room for a source character')
        partial = Fragment(fragment.line, fragment.offset, fragment.text[:best])
        tail = Fragment(fragment.line, fragment.offset + best, fragment.text[best:])
        return [partial], tokens, [tail] + source[i+1:], candidate_memory
    return selected, tokens, [], memory
