"""Request-local namespace translation; never share maps between requests."""
import copy
import hashlib


def alias(namespace, name):
    return 'ns_' + hashlib.sha256((namespace + '\0' + name).encode()).hexdigest()[:40]


def flatten(request):
    req = copy.deepcopy(request)
    flat, mapping, identities = [], {}, set()
    for tool in req.get('tools', []):
        namespace = tool.get('name') if tool.get('type') == 'namespace' else None
        children = tool.get('tools', []) if namespace else [tool]
        for child in children:
            if child.get('type') != 'function':
                raise ValueError('Unsupported child tool type')
            fn = child.get('function', child)
            name = fn['name']
            identity = (namespace, name)
            if identity in identities:
                raise ValueError('Duplicate tool identity')
            identities.add(identity)
            upstream = alias(namespace, name) if namespace else name
            if upstream in mapping:
                raise ValueError('Tool alias collision')
            mapping[upstream] = {'name': name, **({'namespace': namespace} if namespace else {})}
            new = copy.deepcopy(fn)
            new['name'] = upstream
            new['type'] = 'function'
            if namespace:
                new['description'] = ('Namespace: ' + namespace + '. Tool: ' + name + '.\n'
                    + tool.get('description', '') + '\n' + fn.get('description', ''))
            flat.append(new)
    req['tools'] = flat
    if isinstance(req.get('input'), list):
        for item in req['input']:
            if item.get('type') == 'function_call' and item.get('namespace'):
                item['name'] = alias(item.pop('namespace'), item['name'])
    choice = req.get('tool_choice')
    if isinstance(choice, dict) and choice.get('type') == 'function' and choice.get('namespace'):
        choice['name'] = alias(choice.pop('namespace'), choice['name'])
    return req, mapping


def restore(item, mapping):
    if item.get('type') == 'function_call':
        if item['name'] not in mapping:
            raise ValueError('Upstream requested an unadvertised tool')
        item.update(mapping[item['name']])
    return item
