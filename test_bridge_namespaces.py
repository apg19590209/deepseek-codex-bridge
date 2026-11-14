import copy
import unittest
from bridge_namespaces import flatten, restore, alias
from bridge_stream import relay
from test_bridge_stream import chunk, call

class NamespaceTests(unittest.TestCase):
    def request(self):
        return {'tools': [{'type': 'function', 'name': 'exec_command'},
            {'type': 'namespace', 'name': 'multi_agent_v1', 'description': 'agent tools',
             'tools': [{'type': 'function', 'name': 'wait_agent', 'parameters': {'type': 'object'}}]},
            {'type': 'namespace', 'name': 'other', 'tools': [{'type': 'function', 'name': 'wait_agent'}]}]}

    def test_flatten_preserves_all_and_input(self):
        req = self.request()
        saved = copy.deepcopy(req)
        new, mapping = flatten(req)
        self.assertEqual(req, saved)
        self.assertEqual(len(new['tools']), 3)
        self.assertEqual(len(mapping), 3)
        self.assertEqual(new['tools'][0]['name'], 'exec_command')

    def test_roundtrip_stream(self):
        _, mapping = flatten(self.request())
        events = []
        name = alias('multi_agent_v1', 'wait_agent')
        result = relay([chunk(call(name=name, arguments='{}')), chunk(finish='tool_calls'), 'data: [DONE]'],
                       lambda n, v: events.append((n, copy.deepcopy(v))), lambda item: restore(item, mapping))
        self.assertEqual(result['status'], 'completed')
        item = events[-1][1]['response']['output'][0]
        self.assertEqual(item['namespace'], 'multi_agent_v1')
        self.assertEqual(item['name'], 'wait_agent')

    def test_history_and_choice(self):
        req = self.request()
        req['input'] = [{'type': 'function_call', 'name': 'wait_agent', 'namespace': 'multi_agent_v1', 'call_id': 'x'}]
        req['tool_choice'] = {'type': 'function', 'name': 'wait_agent', 'namespace': 'multi_agent_v1'}
        new, _ = flatten(req)
        self.assertEqual(new['input'][0]['name'], new['tool_choice']['name'])
        self.assertEqual(new['input'][0]['call_id'], 'x')

    def test_unknown_call_rejected(self):
        with self.assertRaises(ValueError):
            restore({'type': 'function_call', 'name': 'unadvertised'}, {})

    def test_custom_rejected(self):
        with self.assertRaises(ValueError):
            flatten({'tools': [{'type': 'namespace', 'name': 'x', 'tools': [{'type': 'custom', 'name': 'patch'}]}]})

    def test_collision_rejected(self):
        req = self.request()
        req['tools'].append({'type': 'function', 'name': alias('multi_agent_v1', 'wait_agent')})
        with self.assertRaises(ValueError):
            flatten(req)

if __name__ == '__main__':
    unittest.main()
