from __future__ import annotations

import json,threading,unittest
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from agent_execution_plane.execution import Capability,ExecutionEngine,ExecutionRequest
from agent_execution_plane.providers import OllamaExecutionAdapter,OpenAIExecutionAdapter,TransportNames

class Handler(BaseHTTPRequestHandler):
    requests=[];reply={};replies=[];require_ollama_tool_name=False
    def log_message(self,*_):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['content-length'])));type(self).requests.append((self.path,body,self.headers.get('authorization')))
        if type(self).require_ollama_tool_name and self.path=='/api/chat' and len(type(self).requests)>1 and body.get('messages',[])[-1].get('tool_name')!='only_source_tool':
            self.send_response(422);self.end_headers();return
        reply=type(self).replies.pop(0) if type(self).replies else type(self).reply
        data=json.dumps(reply).encode();self.send_response(200);self.send_header('content-type','application/json');self.send_header('content-length',str(len(data)));self.end_headers();self.wfile.write(data)

class Store:
    def __init__(self,family,url):self.family=family;self.url=url
    def execution_models(self):return [{'id':'m','provider_family':self.family,'base_url':self.url,'provider_model':'reasoner','credential':None,'timeout_minutes':1}]
    def begin_use(self,_):pass
    def end_use(self,_):pass
class Mcp:
    def __init__(self,cap):self.cap=cap;self.calls=[]
    async def list_tools(self,cursor=None):return [self.cap],None
    async def changed(self):return False
    async def call_tool(self,name,arguments):self.calls.append((name,arguments));return {'observed':arguments['x']}

class ProviderExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        Handler.requests=[];Handler.replies=[];Handler.require_ollama_tool_name=False;self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url=f'http://127.0.0.1:{self.server.server_port}'
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

    async def run_loop(self,family,replies):
        Handler.replies=list(replies);mcp=Mcp(self.cap)
        @asynccontextmanager
        async def session(_):yield mcp
        factory=lambda model: OllamaExecutionAdapter(model) if family=='ollama_compatible' else OpenAIExecutionAdapter(model)
        engine=ExecutionEngine(Store(family,self.url),factory,session)
        outcome=await engine.execute(ExecutionRequest('e','s','objective',{},'http://mcp',None,(self.cap,)))
        return outcome,mcp

    async def test_complete_ollama_loop_uses_tool_name(self):
        Handler.require_ollama_tool_name=True
        first={'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'only_source_tool','arguments':{'x':5}}}]}}
        final={'message':{'role':'assistant','content':'ollama done'}}
        outcome,mcp=await self.run_loop('ollama_compatible',[first,final]);self.assertTrue(outcome.success);self.assertEqual(mcp.calls,[('only_source_tool',{'x':5})])
        second=Handler.requests[1][1];tool=second['messages'][-1];self.assertEqual(tool,{'role':'tool','tool_name':'only_source_tool','content':'{"observed":5}'})

    async def test_complete_openai_loop_uses_tool_call_id(self):
        first={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'call-7','type':'function','function':{'name':'only_source_tool','arguments':'{"x":7}'}}]}}]}
        final={'choices':[{'message':{'role':'assistant','content':'openai done'}}]}
        outcome,mcp=await self.run_loop('openai_compatible',[first,final]);self.assertTrue(outcome.success);self.assertEqual(mcp.calls,[('only_source_tool',{'x':7})])
        self.assertEqual(Handler.requests[1][1]['messages'][-1],{'role':'tool','tool_call_id':'call-7','content':'{"observed":7}'})

    async def test_openai_transport_aliases_are_stable_reversible_and_collision_safe(self):
        compatible=Capability('short_name','',{});long1=Capability('acp.'+'same-prefix-'*8+'one','',{});long2=Capability('acp.'+'same-prefix-'*8+'two','',{})
        names=TransportNames((compatible,long1,long2),constrained=True);self.assertEqual(names.source_to_transport['short_name'],'short_name')
        aliases=[names.source_to_transport[long1.name],names.source_to_transport[long2.name]];self.assertNotEqual(*aliases);self.assertTrue(all(len(x)<=64 for x in aliases));self.assertTrue(all(names.source(x)==source.name for x,source in zip(aliases,(long1,long2))))

    async def test_alias_call_dispatches_exact_source_name(self):
        long=Capability('acp.'+'very-long-capability-'*5,'source',{'type':'object','properties':{'x':{'type':'integer'}},'required':['x']});names=TransportNames((long,),constrained=True);alias=names.source_to_transport[long.name]
        Handler.replies=[{'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'c','type':'function','function':{'name':alias,'arguments':'{"x":9}'}}]}}]},{'choices':[{'message':{'role':'assistant','content':'done'}}]}]
        self.cap=long;out,mcp=await self.run_loop('openai_compatible',Handler.replies);self.assertTrue(out.success);self.assertEqual(mcp.calls,[(long.name,{'x':9})]);self.assertEqual(Handler.requests[0][1]['tools'][0]['function']['name'],alias)

if __name__=='__main__':unittest.main()
