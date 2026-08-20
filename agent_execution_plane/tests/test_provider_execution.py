from __future__ import annotations

import json,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from agent_execution_plane.execution import Capability
from agent_execution_plane.providers import OllamaExecutionAdapter,OpenAIExecutionAdapter

class Handler(BaseHTTPRequestHandler):
    requests=[];reply={}
    def log_message(self,*_):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['content-length'])));type(self).requests.append((self.path,body,self.headers.get('authorization')))
        data=json.dumps(type(self).reply).encode();self.send_response(200);self.send_header('content-type','application/json');self.send_header('content-length',str(len(data)));self.end_headers();self.wfile.write(data)

class ProviderExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        Handler.requests=[];self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.cap=Capability('only_source_tool','source description',{'type':'object','properties':{'x':{'type':'integer'}},'required':['x']})
    def tearDown(self):self.server.shutdown();self.server.server_close()
    async def test_openai_tool_and_structured_mapping(self):
        Handler.reply={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'c1','type':'function','function':{'name':'only_source_tool','arguments':'{"x":2}'}}]}}]}
        model={'base_url':self.url,'provider_model':'reasoner','credential':'secret'};reply=await OpenAIExecutionAdapter(model).turn([{'role':'user','content':'x'}],(self.cap,),{'type':'object'},2,None)
        self.assertEqual(reply.tool_calls[0].arguments,{'x':2});path,payload,auth=Handler.requests[0];self.assertEqual(path,'/v1/chat/completions');self.assertEqual(auth,'Bearer secret');self.assertEqual(payload['tools'][0]['function']['name'],'only_source_tool');self.assertEqual(payload['response_format']['type'],'json_schema')
    async def test_ollama_tool_and_format_mapping(self):
        Handler.reply={'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'only_source_tool','arguments':{'x':3}}}]}}
        model={'base_url':self.url,'provider_model':'reasoner','credential':None};reply=await OllamaExecutionAdapter(model).turn([{'role':'user','content':'x'}],(self.cap,),{'type':'object'},2,None)
        self.assertEqual(reply.tool_calls[0].arguments,{'x':3});path,payload,_=Handler.requests[0];self.assertEqual(path,'/api/chat');self.assertEqual(payload['format'],{'type':'object'});self.assertEqual(len(payload['tools']),1)

if __name__=='__main__':unittest.main()
