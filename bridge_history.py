"""Translate text/function history without inventing tool results."""
import json


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if all(isinstance(p, dict) and p.get('type') in ('input_text', 'output_text', 'text') for p in value):
            return '\n'.join(p.get('text', '') for p in value)
        raise ValueError('Unsupported non-text content')
    if value is None:
        return ''
    return json.dumps(value, ensure_ascii=False)


def history(req):
    messages = []
    if req.get('instructions'):
        messages.append({'role': 'system', 'content': req['instructions']})
    inp = req.get('input', [])
    if isinstance(inp, str):
        return messages + [{'role': 'user', 'content': inp}]
    # Chat Completions expects instruction messages ahead of conversation turns.
    # Preserve the relative order of all developer/system messages there.
    if isinstance(inp, list):
        for item in inp:
            if item.get('type', 'message') == 'message' and item.get('role') in ('system', 'developer'):
                messages.append({'role': 'system', 'content': text_content(item.get('content', ''))})
    texts, calls, outputs = [], [], {}

    def flush():
        if calls:
            ids = [c['id'] for c in calls]
            if len(set(ids)) != len(ids) or set(ids) != set(outputs):
                raise ValueError('Missing, duplicate or unmatched tool results')
            messages.append({'role': 'assistant', 'content': '\n'.join(texts), 'tool_calls': list(calls)})
            for cid in ids:
                messages.append({'role': 'tool', 'tool_call_id': cid, 'content': outputs[cid]})
        elif texts:
            messages.append({'role': 'assistant', 'content': '\n'.join(texts)})
        texts.clear()
        calls.clear()
        outputs.clear()

    for item in inp:
        kind = item.get('type', 'message')
        if kind == 'message':
            role = item.get('role', 'user')
            content = text_content(item.get('content', ''))
            if role == 'assistant':
                if calls and len(outputs) == len(calls):
                    flush()
                # Chat Completions has no Responses phase field. Preserve it as
                # an explicit history label, rather than pretending it is final.
                if item.get('phase') == 'commentary':
                    content = '[Assistant progress update; not a final answer]\n' + content
                texts.append(content)
            else:
                flush()
                if role not in ('system', 'developer', 'user'):
                    raise ValueError('Unsupported message role')
                if role == 'user':
                    messages.append({'role': role, 'content': content})
        elif kind == 'function_call':
            if calls and len(outputs) == len(calls):
                flush()
            cid = item.get('call_id')
            if not cid:
                raise ValueError('Tool call lacks call_id')
            calls.append({'id': cid, 'type': 'function', 'function': {
                'name': item['name'], 'arguments': item.get('arguments', '{}')}})
        elif kind == 'function_call_output':
            cid = item['call_id']
            if cid in outputs or cid not in {c['id'] for c in calls}:
                raise ValueError('Duplicate or orphan tool result')
            outputs[cid] = text_content(item.get('output', ''))
        elif kind == 'reasoning':
            # Existing bridge is non-thinking; opaque reasoning is not text.
            continue
        else:
            raise ValueError('Unsupported history item')
    flush()
    return messages
