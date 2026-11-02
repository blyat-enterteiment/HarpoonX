"""XXIV HTTP integration. Synthetic provider only: no paid calls or broker access."""
import io
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from app24 import IntegratedGateway, integrated_handler, DEFAULT_CONFIG, Sessions, validate_config
from test_server import RECIPE

KEY = 'sk-SYNTHETIC-NEVER-A-REAL-CREDENTIAL-12345'
TOKEN = 'SYNTHETIC-ADMIN-ACCESS-NOT-REAL-1234567890'
ROOT = Path(__file__).resolve().parents[1]

class IntegratedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []
        self.fail = False
        def mock(req, timeout):
            self.calls.append(req)
            if self.fail:
                raise TimeoutError('SYNTHETIC TIMEOUT')
            if req.method == 'GET':
                return io.BytesIO(json.dumps({'id':'gpt-6-astra'}).encode())
            raw = dict(id='synthetic-response', status='completed', usage={'input_tokens':100,'output_tokens':50},
                       output=[{'content':[{'type':'output_text','text':json.dumps({'recipe':dict(RECIPE),'findings':[]})}]}])
            return io.BytesIO(json.dumps(raw).encode())
        self.opener = mock
        self.slot = IntegratedGateway(Path(self.tmp.name), opener=mock)
        self.http = ThreadingHTTPServer(('127.0.0.1',0), lambda *a:None)
        self.origin = 'http://127.0.0.1:'+str(self.http.server_port)
        self.http.RequestHandlerClass = integrated_handler(self.slot,TOKEN,self.origin,ROOT/'HARPOON_XXIV.html')
        self.thread = threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.cookie = '';self.csrf = ''
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,origin=None,cookie=True,csrf=True,extra=None):
        headers = {'Origin':origin or self.origin}
        if cookie and self.cookie:headers['Cookie']=self.cookie
        if csrf and self.csrf:headers['X-Harpoon-CSRF']=self.csrf
        if body is not None:headers['Content-Type']='application/json'
        headers.update(extra or {})
        req=urllib.request.Request(self.origin+path, data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:r=urllib.request.urlopen(req,timeout=3)
        except urllib.error.HTTPError as error:r=error
        data=r.read();ct=r.headers.get('Content-Type','')
        return r.status,json.loads(data) if 'json' in ct else data,r.headers
    def login(self):
        status,data,h=self.request('/v1/session',{'token':TOKEN});self.assertEqual(status,200)
        self.cookie=h['Set-Cookie'].split(';')[0];self.csrf=data['csrf'];return h
    def configured(self):
        self.login();c={**DEFAULT_CONFIG,'api_key':KEY}
        self.assertEqual(self.request('/v1/config',c)[0],200);return c
    def job(self,identifier='job-test'):
        return dict(id=identifier,run_id='run-test',budget_usd=5,max_iterations=8,context={'audit':[]})
    def test_html_and_bootstrap_without_key(self):
        status,html,_=self.request('/');self.assertEqual(status,200);self.assertIn(b'HARPOON XXIV',html)
        self.assertEqual(self.request('/v1/bootstrap')[1]['schema'],'HARPOON-INTEGRATED-24');self.assertFalse(self.calls)
    def test_unconfigured_is_explicit_503(self):
        self.login();status,data,_=self.request('/v1/health');self.assertEqual(status,503);self.assertIn('Guarda',data['error'])
    def test_health_requires_authentication(self):
        self.assertEqual(self.request('/v1/health')[0],401)
        self.assertEqual(self.request('/v1/config')[0],401)
    def test_session_cookie_not_exposed_in_body(self):
        headers=self.login();self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        data=self.request('/v1/session')[1];self.assertNotIn(TOKEN,json.dumps(data));self.assertEqual(data['csrf'],self.csrf)
    def test_bad_token_and_cross_origin_login(self):
        self.assertEqual(self.request('/v1/session',{'token':'bad'})[0],401)
        self.assertEqual(self.request('/v1/session',{'token':TOKEN},origin='https://evil.invalid')[0],403)
    def test_duplicate_content_length_rejected_before_login(self):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        data=json.dumps({'token':TOKEN}).encode()
        try:
            connection.putrequest('POST','/v1/session')
            connection.putheader('Origin',self.origin)
            connection.putheader('Content-Type','application/json')
            connection.putheader('Content-Length',str(len(data)))
            connection.putheader('Content-Length',str(len(data)))
            connection.endheaders(data)
            response=connection.getresponse();response.read()
            self.assertEqual(response.status,400)
        finally:connection.close()
    def test_csrf_and_cross_origin_config_blocked(self):
        self.login();c={**DEFAULT_CONFIG,'api_key':KEY}
        self.assertEqual(self.request('/v1/config',c,csrf=False)[0],401)
        self.assertEqual(self.request('/v1/config',c,origin='https://evil.invalid')[0],401);self.assertIsNone(self.slot.config)
    def test_persistent_encrypted_config_and_secret_redaction(self):
        self.configured();payload=self.request('/v1/config')[1];self.assertNotIn(KEY,json.dumps(payload));self.assertNotIn('api_key',payload['config'])
        path=Path(self.tmp.name)/'gateway.enc';self.assertNotIn(KEY.encode(),path.read_bytes());self.assertEqual(path.stat().st_mode&0o777,0o600)
        other=IntegratedGateway(Path(self.tmp.name),opener=self.opener);self.assertEqual(other.config['api_key'],KEY)
    def test_health_never_calls_provider(self):
        self.configured();status,data,_=self.request('/v1/health');self.assertEqual(status,200);self.assertEqual(data['integrated_gateway'],'24.0.0');self.assertFalse(self.calls)
    def test_configured_prices_do_not_claim_external_verification(self):
        self.configured();data=self.request('/v1/config')[1]
        self.assertIsNone(data['prices_verified_on'])
        self.assertEqual(data['pricing_status'],'operator_configured_not_verified')
        self.assertFalse(self.calls)
    def test_key_check_uses_fixed_model_url_no_generation(self):
        self.configured();status,data,_=self.request('/v1/provider-check',{});self.assertEqual(status,200);self.assertEqual(data['generation_tokens'],0)
        self.assertEqual(self.calls[0].full_url,'https://api.openai.com/v1/models/gpt-6-astra');self.assertEqual(self.calls[0].method,'GET')
        self.assertEqual(self.request('/v1/provider-check',{})[0],429)
    def test_key_check_failure_is_explicit(self):
        self.configured();self.fail=True;status,data,_=self.request('/v1/provider-check',{});self.assertEqual(status,502);self.assertNotIn(KEY,json.dumps(data))
    def test_legacy_bearer_transport_preserved(self):
        self.configured();self.assertEqual(self.request('/v1/health',cookie=False,extra={'Authorization':'Bearer '+TOKEN})[0],200)
    def test_cold_request_idempotency_and_same_sqlite_budget(self):
        self.configured();status,data,_=self.request('/v1/jobs',self.job());self.assertEqual(status,200)
        for _ in range(50):
            result=self.request('/v1/jobs/job-test')[1]
            if result['status']!='pending':break
            time.sleep(.01)
        self.assertEqual(result['status'],'completed');self.assertGreater(result['cost_usd'],0)
        self.request('/v1/jobs',self.job());self.assertEqual(len(self.calls),1)
        health=self.request('/v1/health')[1];self.assertGreater(health['supervision']['totals']['month_usd'],0)
    def test_hot_policy_same_contract_and_csrf(self):
        self.configured();health=self.request('/v1/health')[1];p=health['supervision']['policy'];p['enabled']=True
        self.assertEqual(self.request('/v1/review-policy',p,csrf=False)[0],401)
        self.assertEqual(self.request('/v1/review-policy',p)[0],200)
    def test_hot_http_response_preserves_read_only_and_model(self):
        from supervision import fingerprint
        self.configured();p=self.slot.gateway.reviews.policy();p['enabled']=True
        self.request('/v1/review-policy',p)
        context=dict(schema='HARPOON-XXI-SNAPSHOT-1',snapshot_id='qa-hot',account_ref='a'*64,
                     book='securities',captured_at=int(time.time()*1000),window=dict(start=1,end=2,key='qa-window'),
                     config_hash='b'*64,plugin_hash='c'*64,evidence=[dict(id='qa-evidence',kind='realized',value={'basis':'SYNTHETIC'})])
        req=dict(id='hot-test',policy_revision=fingerprint(p),material_hash='d'*64,context=context)
        def mock(request,timeout):
            self.calls.append(request);payload=json.loads(request.data)
            self.assertNotIn('tools',payload)
            result={k:context[k] for k in ['snapshot_id','config_hash','plugin_hash']}
            result.update(verdict='insufficient_evidence',findings=[],next_review_reason='SYNTHETIC TEST')
            return io.BytesIO(json.dumps(dict(id='qa-hot-response',status='completed',usage={'input_tokens':100,'output_tokens':50},output=[{'content':[{'type':'output_text','text':json.dumps(result)}]}])).encode())
        self.slot.gateway.opener=mock
        self.assertEqual(self.request('/v1/reviews',req)[0],202)
        for _ in range(100):
            job=self.request('/v1/reviews/hot-test')[1]
            if job['status'] not in ('pending','running'):break
            time.sleep(.01)
        self.assertEqual(job['status'],'completed');self.assertEqual(job['model'],'gpt-6-astra')
        self.request('/v1/reviews',req);self.assertEqual(len(self.calls),1)

    def test_pending_or_unknown_prevents_configuration_change(self):
        c=self.configured();self.fail=True;job=self.slot.submit(self.job(),False);self.assertEqual(job['status'],'unknown')
        self.assertEqual(self.request('/v1/config',c)[0],409);self.assertEqual(self.slot.get(job['id'])['cost_usd'],job['cost_usd'])
    def test_reload_preserves_spend_and_work_ids(self):
        c=self.configured();j=self.slot.submit(self.job(),False)
        c['api_key']='';self.assertEqual(self.request('/v1/config',c)[0],200)
        self.assertEqual(self.slot.get(j['id'])['cost_usd'],j['cost_usd']);self.assertEqual(self.slot.config['api_key'],KEY)
    def test_logout_revokes_cookie_no_broker_side_effect(self):
        self.configured();self.assertEqual(self.request('/v1/logout',{})[0],200)
        self.assertEqual(self.request('/v1/config')[0],401);self.assertIsNotNone(self.slot.gateway);self.assertFalse(self.calls)
    def test_no_secret_file_serving(self):
        self.configured()
        for path in ['/gateway.enc','/../gateway.master','/service/server.py','/.env']:
            self.assertEqual(self.request(path)[0],404)
    def test_invalid_config_rejected_without_changes(self):
        c=self.configured()
        for edit in [{'input_rate':-1},{'cached_rate':50},{'api_key':'bad'},{'model':'https://evil.invalid'},{'risk':99}]:
            self.assertEqual(self.request('/v1/config',{**c,**edit})[0],400)
        self.assertEqual(self.slot.config['input_rate'],10)
    def test_remote_plain_http_origin_rejected(self):
        with self.assertRaises(ValueError):integrated_handler(self.slot,TOKEN,'http://remote.invalid',ROOT/'HARPOON_XXIV.html')
    def test_corrupt_vault_never_resets(self):
        self.configured();(Path(self.tmp.name)/'gateway.enc').write_bytes(b'bad')
        with self.assertRaises(Exception):IntegratedGateway(Path(self.tmp.name))
    def test_session_expiry_and_login_rate_limit(self):
        s=Sessions(TOKEN,ttl=-1);sid,_=s.login(TOKEN);self.assertIsNone(s.get(sid))
        s=Sessions(TOKEN)
        for _ in range(12):
            with self.assertRaises(ValueError):s.login('wrong')
        with self.assertRaises(ValueError) as error:s.login(TOKEN)
        self.assertEqual(error.exception.status,429)
    def test_historical_model_survives_reconfiguration(self):
        c=self.configured();j=self.slot.submit(self.job(),False)
        c['model']='other-configured-model';c['api_key']=''
        self.assertEqual(self.request('/v1/config',c)[0],200)
        self.assertEqual(self.slot.get(j['id'])['model'],'gpt-6-astra')
        self.assertEqual(self.slot.health()['model'],'other-configured-model')

    def test_no_unbounded_settings_and_nan(self):
        for v in [float('nan'),float('inf'),1001,True]:
            with self.assertRaises(ValueError):validate_config({**DEFAULT_CONFIG,'api_key':KEY,'monthly_cap':v})

if __name__=='__main__':unittest.main(verbosity=2)
