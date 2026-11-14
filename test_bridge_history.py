import unittest
from bridge_history import history

def call(cid='a'):
    return {'type': 'function_call', 'name': 'inspect', 'call_id': cid, 'arguments': '{}'}

def result(cid='a', value='done'):
    return {'type': 'function_call_output', 'call_id': cid, 'output': value}

def comment(text='working'):
    return {'role': 'assistant', 'phase': 'commentary', 'content': text}

class HistoryTests(unittest.TestCase):
    def convert(self, *items):
        return history({'input': list(items)})

    def test_text_and_call_grouped(self):
        m = self.convert(comment(), call(), result())
        self.assertEqual(len(m), 2)
        self.assertIn('not a final answer', m[0]['content'])
        self.assertEqual(m[0]['tool_calls'][0]['id'], 'a')

    def test_intervening_commentary_no_fabrication(self):
        m = self.convert(call(), comment(), result())
        self.assertEqual(len(m), 2)
        self.assertEqual(m[1]['content'], 'done')

    def test_structured_text(self):
        m = self.convert(call(), result(value=[{'type': 'input_text', 'text': 'actual'}]))
        self.assertEqual(m[-1]['content'], 'actual')

    def test_two_rounds(self):
        m = self.convert(comment(), call(), result(), comment('next'), call('b'), result('b'))
        self.assertEqual([x['role'] for x in m], ['assistant','tool','assistant','tool'])

    def test_missing_and_duplicate_rejected(self):
        for items in ([call()], [result()], [call(), result(), result()]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                self.convert(*items)

    def test_parallel_results(self):
        m = self.convert(call(), call('b'), result('b'), result())
        self.assertEqual([x.get('tool_call_id') for x in m[1:]], ['a','b'])

    def test_roles_and_plain_input(self):
        self.assertEqual(history({'input':'hello'})[0]['content'], 'hello')
        self.assertEqual(self.convert({'role':'developer','content':'rule'})[0]['role'], 'system')

    def test_unsupported_image_rejected(self):
        with self.assertRaises(ValueError):
            self.convert({'role':'user','content':[{'type':'input_image','image_url':'secret'}]})

    def test_late_developer_instruction_is_hoisted(self):
        m = self.convert({'role':'user','content':'question'}, comment(),
            {'role':'developer','content':'rule'})
        self.assertEqual([x['role'] for x in m], ['system','user','assistant'])
        self.assertEqual(m[0]['content'], 'rule')

if __name__ == '__main__':
    unittest.main()
