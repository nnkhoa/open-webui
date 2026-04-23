import json
import re


def clean_sql(text: str) -> str:
    # Strip thinking tags first
    text = re.sub(r'<thinking>[\s\S]*?</thinking>', '', text, flags=re.IGNORECASE).strip()
    if text.startswith("```"):
        # Handle cases like ```sql ... ```
        lines = text.split("\n")
        if len(lines) > 1 and lines[0].strip().lower().startswith("```"):
            text = "\n".join(lines[1:]).rsplit("```", 1)[0].strip()
        else:
            text = text.strip("`").strip()
    # Remove leading 'sql' keyword if it remains
    if text.lower().startswith("sql"):
        text = text[3:].strip()
    return text.strip()

def _find_balanced_json_array_end(s: str) -> int:
    """
    Returns the end index (exclusive) of the first balanced JSON array that starts at s[0] == '['.
    Returns -1 if not found.
    """
    if not s or s[0] != "[":
        return -1

    bracket_count = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(s):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            bracket_count += 1
        elif ch == "]":
            bracket_count -= 1
            if bracket_count == 0:
                return i + 1
    return -1


def _extract_vis_config_candidate(text: str) -> tuple[str | None, tuple[int, int] | None]:
    """
    Extracts VIS_CONFIG payload from text.
    Returns (candidate_json_array, (remove_start, remove_end)) where remove span is the full VIS_CONFIG marker+payload.
    """
    m = re.search(r"VIS_CONFIG\s*[:=]\s*", text, re.I)
    if not m:
        return None, None

    i = m.end()
    # Skip whitespace
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return None, None

    # Case 1: VIS_CONFIG:"[...]" (string-encoded JSON)
    if text[i] in {"'", '"'}:
        quote = text[i]
        j = i + 1
        escape_next = False
        while j < len(text):
            ch = text[j]
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == quote:
                break
            j += 1
        if j >= len(text):
            return None, None

        inner = text[i + 1 : j]
        if quote == '"':
            # Decode JSON-string escapes (\\n, \\", etc.)
            try:
                inner = json.loads(f'"{inner}"')
            except Exception:
                pass
        candidate = inner.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if not candidate.startswith("["):
            return None, None
        return candidate, (m.start(), j + 1)

    # Case 2: VIS_CONFIG:[ ... ]
    start = text.find("[", i)
    if start == -1:
        return None, None

    end_rel = _find_balanced_json_array_end(text[start:])
    if end_rel == -1:
        return None, None
    end = start + end_rel
    return text[start:end], (m.start(), end)


def _try_parse_vis_blocks(candidate: str) -> list | None:
    if not candidate:
        return None
    raw = candidate.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    # Attempt 1: strict JSON
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    # Attempt 2: common LLM over-escaping: [{\"type\":\"...\"}]
    if '\\"' in raw:
        try:
            parsed = json.loads(raw.replace('\\"', '"'))
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    return None


def parse_vis_config(text: str) -> tuple[str, dict | None, list | None]:
    # Strip thinking tags first
    text = re.sub(r'<(thinking|thought|reasoning)>[\s\S]*?<\/\1>', '', text, flags=re.IGNORECASE).strip()
    
    chart_config = None
    blocks = None

    candidate, remove_span = _extract_vis_config_candidate(text)
    parsed_blocks = _try_parse_vis_blocks(candidate) if candidate else None
    if isinstance(parsed_blocks, list) and len(parsed_blocks) > 0:
        blocks = parsed_blocks
        for b in parsed_blocks:
            if isinstance(b, dict) and b.get("type") == "chart":
                chart_config = {
                    "type": b.get("chartType", "bar"),
                    "xKey": b.get("xKey", ""),
                    "yKeys": b.get("yKeys", []),
                    "options": b.get("options"),
                }
                if chart_config["yKeys"]:
                    chart_config["yKey"] = chart_config["yKeys"][0]
                break

    # 2. Fallback: If no VIS_CONFIG array found, try to find individual blocks on separate lines
    if not blocks:
        individual_blocks = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('{') and line.endswith('}') and '"type"' in line:
                try:
                    b = json.loads(line)
                    if "type" in b: individual_blocks.append(b)
                except: pass
        if individual_blocks:
            blocks = individual_blocks
            for b in individual_blocks:
                if b.get("type") == "chart" and not chart_config:
                    chart_config = {
                        "type": b.get("chartType", "bar"),
                        "xKey": b.get("xKey", ""),
                        "yKeys": b.get("yKeys", []),
                        "options": b.get("options"),
                    }
                    if chart_config["yKeys"]:
                        chart_config["yKey"] = chart_config["yKeys"][0]

    clean_lines = []
    remaining_text = text
    if remove_span:
        a, b = remove_span
        remaining_text = (text[:a] + text[b:]).strip()

    for line in remaining_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            clean_lines.append(line)
            continue
        # Sometimes the model wraps the whole response in a JSON-like object and leaves lone braces behind.
        # Remove lines that are just "{" or "}" (optionally with a trailing comma).
        if re.match(r"^[\{\}]\s*,?\s*$", stripped):
            continue
        if re.search(r'CHART_CONFIG\s*:', stripped):
            continue
        if stripped.startswith("```") or stripped == "json":
            continue
        # Skip lines that were parsed as individual blocks
        if stripped.startswith('{') and stripped.endswith('}') and '"type"' in stripped:
            try:
                b = json.loads(stripped)
                if "type" in b: continue
            except: pass
        if not remove_span and (stripped.startswith('[{') or (stripped.startswith('{') and 'type' in stripped)):
            continue
        clean_lines.append(line)

    cleaned = "\n".join(clean_lines).strip()
    # Second pass: drop any remaining standalone brace lines created by multi-line merges.
    if cleaned:
        cleaned_lines = [l for l in cleaned.split("\n") if not re.match(r"^\s*[\{\}]\s*,?\s*$", l.strip())]
        cleaned = "\n".join(cleaned_lines).strip()
        # If the entire remaining text is wrapped in a single outer { ... }, unwrap it.
        if cleaned.startswith("{") and cleaned.endswith("}") and cleaned.count("{") == 1 and cleaned.count("}") == 1:
            cleaned = cleaned[1:-1].strip()

    return cleaned, chart_config, blocks


def stream_parse_blocks(text: str) -> list:
    """Finds balanced { } blocks within the first VIS_CONFIG:[ ] array found in text."""
    vis_match = re.search(r'VIS_CONFIG\s*[:=]\s*\[', text, re.I)
    if not vis_match:
        return []
        
    start_pos = vis_match.end() - 1 # include the [
    content = text[start_pos:]
    
    blocks = []
    bracket_count = 0
    in_string = False
    escape_next = False
    block_start = -1
    
    # We only care about root-level { } inside the [ ]
    # The [ itself is at index 0 of content
    for i, char in enumerate(content):
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '{':
                if bracket_count == 0:
                    block_start = i
                bracket_count += 1
            elif char == '}':
                bracket_count -= 1
                if bracket_count == 0 and block_start != -1:
                    block_str = content[block_start:i+1]
                    try:
                        blocks.append(json.loads(block_str))
                    except:
                        pass
                if bracket_count < 0: # end of array basically
                    break
            elif char == ']':
                if bracket_count == 0:
                    break
                    
    return blocks


def parse_json_array(text: str) -> list[str]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    match = re.search(r"\[[\s\S]*\]", raw)
    candidate = match.group(0) if match else raw
    try:
        parsed = json.loads(candidate)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
