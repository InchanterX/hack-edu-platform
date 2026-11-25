import http.client
import json
import os
import threading
import unittest
from unittest.mock import patch
import app

class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def setUp(self):
        with app.lock:
            app.state.update(attempts=0, records=[], decisions={})
    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, json.dumps(body) if body is not None else None, headers or ({'Content-Type':'application/json'} if body is not None else {}))
        response = conn.getresponse(); raw = response.read(); status = response.status; conn.close()
        return status, json.loads(raw)
    def test_validation(self):
        valid={'scores':[0,1,2], 'comments':[{'text':'Общее замечание','quote':''},{'text':'Да','quote':'вращается'}]}
        self.assertEqual(app.validate(valid, 'Земля вращается.'), [])
        for bad in [None, {}, {'scores':[0,1,3], 'comments':[]}, {'scores':[True,1,2], 'comments':[]}, {'scores':[0,1], 'comments':[]}, {'scores':[0,1,2], 'comments':[{'text':'x','quote':'несуществующая'}]}, {'scores':[0,1,2], 'comments':[{'text':'','quote':''}]}]:
            self.assertTrue(app.validate(bad, 'Земля вращается.'))
    def test_data_missing_key_and_report(self):
        status, data=self.request('GET','/api/data'); self.assertEqual(status,200); self.assertEqual(len(data['answers']),12)
        with patch.dict(os.environ, {}, clear=True), patch.object(app, 'call_model') as model:
            self.assertEqual(self.request('POST','/api/live',{'index':0})[0],400); model.assert_not_called()
        _, report=self.request('GET','/api/report'); self.assertEqual(report['live_status'],'not_run'); self.assertEqual(report['attempts'],0); self.assertIn('Fake',report['fake_checks'])
        self.assertEqual(self.request('POST','/api/decision',{'index':0,'decision':'accepted'})[0],400)
    def test_explicit_calls_limit_decision_and_errors(self):
        result={'scores':[2,2,2], 'comments':[{'text':'ok','quote':''}]}
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test'}), patch.object(app,'call_model',return_value=result) as model:
            self.request('GET','/api/data'); model.assert_not_called()
            for _ in range(15):
                status, record=self.request('POST','/api/live',{'index':0}); self.assertEqual(status,200); self.assertEqual(record['validation'],[])
            self.assertEqual(self.request('POST','/api/live',{'index':0})[0],429); self.assertEqual(model.call_count,15)
            _, decision=self.request('POST','/api/decision',{'index':0,'decision':'accepted'}); self.assertEqual(decision,{'decision':'accepted','published':False})
            _, report=self.request('GET','/api/report'); self.assertEqual(report['live_status'],'attempted'); self.assertEqual(len(report['live_results']),15)
    def test_fake_error_and_invalid_quote(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test'}), patch.object(app,'call_model',side_effect=[ValueError('Сетевая ошибка'), {'scores':[1,1,1],'comments':[{'text':'x','quote':'missing'}]}]):
            _, error=self.request('POST','/api/live',{'index':1}); self.assertEqual(error['error'],'Сетевая ошибка')
            _, invalid=self.request('POST','/api/live',{'index':1}); self.assertTrue(invalid['validation'])
            self.assertEqual(self.request('POST','/api/decision',{'index':1,'decision':'accepted'})[0],400)
            _, report=self.request('GET','/api/report'); self.assertEqual(report['live_results'][0]['error'],'Сетевая ошибка')
    def test_safe_render_and_cross_site(self):
        html=app.Path(app.__file__).with_name('index.html').read_text(); self.assertIn('.textContent',html); self.assertNotIn('innerHTML',html)
        self.assertEqual(self.request('POST','/api/live',{'index':0},{'Content-Type':'application/json','Sec-Fetch-Site':'cross-site'})[0],403)

if __name__ == '__main__': unittest.main()
