from __future__ import annotations

import asyncio,json,threading,tempfile,unittest,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

from agent_execution_plane.codex_runtime import CodexRuntime,bundled_codex
from agent_execution_plane.execution import Capability

def response_object(rid,output,status='completed'):
    return {'id':rid,'object':'response','created_at':0,'status':status,'error':None,'incomplete_details':None,'instructions':None,'max_output_tokens':None,'model':'gpt-test','output':output,'parallel_tool_calls':True,'previous_response_id':None,'reasoning':None,'store':False,'temperature':None,'text':None,'tool_choice':'auto','tools':[],'top_p':None,'truncation':'disabled','usage':{'input_tokens':1,'input_tokens_details':{'cached_tokens':0},'output_tokens':1,'output_tokens_details':{'reasoning_tokens':0},'total_tokens':2},'user':None,'metadata':{}}

def text_events():
    rid='resp_'+uuid.uuid4().hex;item={'id':'msg_'+uuid.uuid4().hex,'type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':'done','annotations':[]}]}
    return [{'type':'response.output_item.done','output_index':0,'item':item},{'type':'response.completed','response':response_object(rid,[item])}]

def call_events(name,arguments):
    rid='resp_'+uuid.uuid4().hex;item={'id':'fc_'+uuid.uuid4().hex,'type':'function_call','status':'completed','name':name,'call_id':'call_'+uuid.uuid4().hex,'arguments':json.dumps(arguments,separators=(',',':'))}
    return [{'type':'response.output_item.done','output_index':0,'item':item},{'type':'response.completed','response':response_object(rid,[item])}]

class Capture(BaseHTTPRequestHandler):
    requests=[];mode='final';calls=0;private_path=''
    def log_message(self,*_):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('content-length','0'))));type(self).requests.append(body);type(self).calls+=1
        if type(self).calls==1 and type(self).mode=='dynamic':events=call_events('source_dynamic',{'value':4})
        elif type(self).calls==1 and type(self).mode=='private':events=call_events('view_image',{'path':type(self).private_path})
        else:events=text_events()
        payload=''.join('data: '+json.dumps(event,separators=(',',':'))+'\n\n' for event in events)+'data: [DONE]\n\n'
        data=payload.encode();self.send_response(200);self.send_header('content-type','text/event-stream');self.send_header('content-length',str(len(data)));self.end_headers();self.wfile.write(data)

class RealCodexGateTests(unittest.TestCase):
    def setUp(self):
        Capture.requests=[];Capture.calls=0;Capture.mode='final';self.server=ThreadingHTTPServer(('127.0.0.1',0),Capture);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.temp.cleanup()
    def runtime(self):
        provider=f'{{ name="Capture", base_url="http://127.0.0.1:{self.server.server_port}", wire_api="responses", requires_openai_auth=false }}'
        command=(bundled_codex(),'app-server','--listen','stdio://','-c',f'model_providers.capture={provider}')
        return CodexRuntime(self.root/'codex-home',command=command,environment={'OPENAI_API_KEY':'must-remove','AEP_MCP_SECRET':'must-not-reach-provider'})
    def execute(self,tools=(),mode='final'):
        Capture.mode=mode;dispatched=[]
        async def run():
            async def dispatch(call):dispatched.append(call);return {'mcp_result':call.arguments}
            reply=await self.runtime().execute_turn('gpt-test',[{'role':'user','content':'public source task'}],tuple(tools),None,15,dispatch,model_provider='capture')
            return reply
        reply=asyncio.run(run());return reply,dispatched
    def aep_names(self,payload):return [tool['name'] for tool in payload['tools'] if tool.get('type')=='function' and tool.get('description','').startswith('AEP_SOURCE:')]
    def test_real_binary_empty_and_n_envelopes_keep_native_helpers_separate(self):
        self.execute();zero=Capture.requests[-1];self.assertEqual(self.aep_names(zero),[])
        native={tool.get('name',tool.get('type')) for tool in zero['tools']};self.assertIn('update_plan',native);self.assertIn('web_search',native)
        self.assertFalse(native & {'exec_command','write_stdin','apply_patch','mcp','spawn_agent'})
        Capture.requests=[];Capture.calls=0
        tools=(Capability('source_one','AEP_SOURCE: one',{'type':'object'}),Capability('source_two','AEP_SOURCE: two',{'type':'object'}))
        self.execute(tools);self.assertEqual(self.aep_names(Capture.requests[0]),['source_one','source_two'])
        serialized=json.dumps(Capture.requests);self.assertNotIn('must-not-reach-provider',serialized);self.assertNotIn('must-remove',serialized)
    def test_real_binary_dynamic_call_returns_through_aep_dispatch(self):
        tool=Capability('source_dynamic','AEP_SOURCE: dynamic',{'type':'object','properties':{'value':{'type':'integer'}},'required':['value']})
        reply,calls=self.execute((tool,),'dynamic');self.assertEqual(reply.content,'done');self.assertEqual([(c.name,c.arguments) for c in calls],[('source_dynamic',{'value':4})]);self.assertGreaterEqual(len(Capture.requests),2)
    def test_real_binary_view_image_cannot_exfiltrate_private_text_secret(self):
        secret='AEP_PRIVATE_CREDENTIAL_MUST_NOT_LEAK';private=self.root/'codex-home'/'private-credential.txt';private.parent.mkdir(parents=True,exist_ok=True);private.write_text(secret);Capture.private_path=str(private)
        self.execute(mode='private');self.assertNotIn(secret,json.dumps(Capture.requests));self.assertGreaterEqual(len(Capture.requests),2)

if __name__=='__main__':unittest.main()
