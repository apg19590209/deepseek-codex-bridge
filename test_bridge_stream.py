import copy
import json
import unittest
from bridge_stream import relay

def chunk(delta=None, finish=None):
    return 'data: ' + json.dumps({'choices': [{'delta': delta or {}, 'finish_reason': finish}]})

def call(index=0, **fn):
    return {'tool_calls': [{'index': index, 'id': 'call_' + str(index), 'function': fn}]}

class StreamTests(unittest.TestCase):
    def run_stream(self, lines):
        events = []
        result = relay(lines, lambda name, value: events.append((name, copy.deepcopy(value))))
        return result, events

    def test_text_stop(self):
        result, events = self.run_stream([chunk({'content': 'I will inspect'}), chunk(finish='stop'), 'data: [DONE]'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['tool_count'], 0)

    def test_tool_before_text_unique_indexes(self):
        result, events = self.run_stream([chunk(call(name='inspect', arguments='{}')),
            chunk({'content': 'Inspecting'}), chunk(finish='tool_calls'), 'data: [DONE]'])
        added = [v['output_index'] for n, v in events if n == 'response.output_item.added']
        self.assertEqual(sorted(added), [0, 1])
        self.assertEqual(result['status'], 'completed')

    def test_fragmented_tool(self):
        result, events = self.run_stream([chunk(call(name='in', arguments='{')),
            chunk({'tool_calls': [{'index': 0, 'function': {'name': 'spect', 'arguments': '}'}}]}),
            chunk(finish='tool_calls'), 'data: [DONE]'])
        self.assertEqual(events[-1][1]['response']['output'][0]['name'], 'inspect')
        self.assertEqual(result['status'], 'completed')

    def test_incomplete_and_errors_never_complete(self):
        for lines in ([chunk({'content': 'working'})], ['data: [DONE]'], ['data: invalid'],
                      ['data: {"error": {"message": "secret"}}'],
                      [chunk(call(name='x', arguments='{')), chunk(finish='tool_calls'), 'data: [DONE]']):
            with self.subTest(lines=lines):
                result, events = self.run_stream(lines)
                self.assertEqual(result['status'], 'failed')
                self.assertFalse(any(n == 'response.completed' for n, _ in events))
                self.assertFalse(any(n == 'response.output_item.done' for n, _ in events))

    def test_length_is_incomplete(self):
        result, _ = self.run_stream([chunk(finish='length'), 'data: [DONE]'])
        self.assertEqual(result['status'], 'incomplete')

    def test_two_tools(self):
        result, events = self.run_stream([chunk(call(name='a', arguments='{}')),
            chunk(call(index=1, name='b', arguments='{}')), chunk(finish='tool_calls'), 'data: [DONE]'])
        self.assertEqual(result['tool_count'], 2)
        self.assertEqual(len(events[-1][1]['response']['output']), 2)

    def test_tool_then_text_has_terminal_events_in_order(self):
        result, events = self.run_stream([chunk(call(name='inspect', arguments='{}')),
            chunk({'content': 'working'}), chunk(finish='tool_calls'), 'data: [DONE]'])
        self.assertEqual(result['status'], 'completed')
        added = [(i, v['output_index']) for i, (n, v) in enumerate(events)
                 if n == 'response.output_item.added']
        self.assertEqual([x[1] for x in added], [0, 1])
        self.assertLess(added[0][0], added[1][0])
        self.assertEqual(len([1 for n, _ in events if n == 'response.output_item.done']), 2)
        self.assertEqual(len([1 for n, _ in events if n == 'response.output_text.done']), 1)

    def test_tool_with_stop_fails(self):
        result, events = self.run_stream([chunk(call(name='inspect', arguments='{}')),
            chunk(finish='stop'), 'data: [DONE]'])
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(any(n == 'response.completed' for n, _ in events))

if __name__ == '__main__':
    unittest.main()
