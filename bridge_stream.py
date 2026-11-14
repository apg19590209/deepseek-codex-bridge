"""Validated Chat Completions stream -> Responses events (no network access)."""
import json
import uuid


def relay(lines, emit, transform_call=None):
    rid = 'resp_' + uuid.uuid4().hex
    emit('response.created', {'response': {'id': rid, 'status': 'in_progress', 'output': []}})
    items, calls = [], {}
    text_item = None
    finish = None
    done = False
    try:
        for raw in lines:
            line = raw.decode('utf-8').strip() if isinstance(raw, bytes) else raw.strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                done = True
                break
            chunk = json.loads(data)
            if chunk.get('error'):
                raise ValueError('Upstream reported an error')
            choices = chunk.get('choices', [])
            if not choices:
                continue
            choice = choices[0]
            if choice.get('finish_reason') is not None:
                finish = choice['finish_reason']
            delta = choice.get('delta', {})
            if delta.get('content'):
                if text_item is None:
                    text_item = {'id': 'msg_' + uuid.uuid4().hex, 'type': 'message',
                                 'role': 'assistant', 'status': 'in_progress', 'content': []}
                    items.append(text_item)
                    index = len(items) - 1
                    part = {'type': 'output_text', 'text': '', 'annotations': []}
                    text_item['content'] = [part]
                index = items.index(text_item)
                text_item['content'][0]['text'] += delta['content']
            for call in delta.get('tool_calls', []):
                key = call['index']
                fn = call.get('function', {})
                if key not in calls:
                    calls[key] = {'id': 'fc_' + uuid.uuid4().hex, 'type': 'function_call',
                                  'call_id': '', 'name': '', 'arguments': '', 'status': 'in_progress'}
                    items.append(calls[key])
                item = calls[key]
                if call.get('id'):
                    item['call_id'] = call['id']
                item['name'] += fn.get('name', '')
                item['arguments'] += fn.get('arguments', '')
        if not done or finish not in ('stop', 'tool_calls', 'length', 'content_filter'):
            raise ValueError('Missing or unsupported upstream completion marker')
        if finish in ('length', 'content_filter'):
            emit('response.incomplete', {'response': {'id': rid, 'status': 'incomplete', 'output': [],
                 'incomplete_details': {'reason': 'max_output_tokens' if finish == 'length' else 'content_filter'}}})
            return {'finish_reason': finish, 'tool_count': len(calls), 'status': 'incomplete'}
        if calls and finish != 'tool_calls':
            raise ValueError('Tool calls and finish reason disagree')
        if finish == 'tool_calls' and not calls:
            raise ValueError('Tool finish without calls')
        for item in calls.values():
            if not item['call_id'] or not item['name']:
                raise ValueError('Incomplete tool identity')
            if not isinstance(json.loads(item['arguments']), dict):
                raise ValueError('Tool arguments must be a JSON object')
            if transform_call:
                transform_call(item)
        for index, item in enumerate(items):
            if item['type'] == 'function_call':
                # Buffer tool fragments until validated; never expose a partial executable call.
                initial = dict(item, arguments='', status='in_progress')
                emit('response.output_item.added', {'output_index': index, 'item': initial})
                emit('response.function_call_arguments.done', {'item_id': item['id'], 'output_index': index,
                     'arguments': item['arguments']})
            else:
                part = item['content'][0]
                emit('response.output_item.added', {'output_index': index, 'item': dict(item, content=[])})
                emit('response.content_part.added', {'item_id': item['id'], 'output_index': index,
                     'content_index': 0, 'part': {'type': 'output_text', 'text': '', 'annotations': []}})
                emit('response.output_text.delta', {'item_id': item['id'], 'output_index': index,
                     'content_index': 0, 'delta': part['text']})
                emit('response.output_text.done', {'item_id': item['id'], 'output_index': index,
                     'content_index': 0, 'text': part['text']})
                emit('response.content_part.done', {'item_id': item['id'], 'output_index': index,
                     'content_index': 0, 'part': part})
            item['status'] = 'completed'
            emit('response.output_item.done', {'output_index': index, 'item': item})
        emit('response.completed', {'response': {'id': rid, 'status': 'completed', 'output': items}})
        return {'finish_reason': finish, 'tool_count': len(calls), 'status': 'completed'}
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        emit('response.failed', {'response': {'id': rid, 'status': 'failed', 'output': [],
             'error': {'code': 'bridge_stream_error', 'message': 'Invalid or incomplete upstream stream; no tool calls forwarded.'}}})
        return {'finish_reason': finish, 'tool_count': len(calls), 'status': 'failed'}
