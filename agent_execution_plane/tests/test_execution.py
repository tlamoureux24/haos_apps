from __future__ import annotations

import asyncio, json, unittest
from contextlib import asynccontextmanager

from agent_execution_plane.execution import *

SCHEMA={'type':'object','properties':{'value':{'type':'integer'}},'required':['value'],'additionalProperties':False}

class Store:
    def __init__(self,models=None):
        self.models=models or [{'id':'m1','provider_family':'fake','timeout_minutes':1}];self.used=[]
    def execution_models(self): return [dict(x) for x in self.models if x.get('enabled',True)]
    def begin_use(self,i): self.used.append(('begin',i))
    def end_use(self,i): self.used.append(('end',i))

class Mcp:
    def __init__(self,inventory=(),pages=None,result=None,fail=False,changed=False,block=None):
        self.inventory=list(inventory);self.pages=pages;self.result=result if result is not None else {'ok':True};self.fail=fail;self.calls=[];self.change=changed;self.block=block
    async def list_tools(self,cursor=None):
        if self.pages:
            index=int(cursor or 0); return self.pages[index],str(index+1) if index+1<len(self.pages) else None
        return self.inventory,None
    async def call_tool(self,name,arguments):
        self.calls.append((name,arguments))
        if self.block: await self.block.wait()
        if self.fail: raise RuntimeError
        return self.result
    async def changed(self): value,self.change=self.change,False;return value

class ReplyProvider:
    def __init__(self,replies=None,error=None,seen=None):self.replies=list(replies or []);self.error=error;self.seen=seen
    async def turn(self,messages,tools,schema,remaining,dispatch):
        if self.seen is not None:self.seen.append((messages,tools,schema,remaining))
        if self.error: raise self.error
        return self.replies.pop(0)

def request(caps=(),schema=None,guard=None):return ExecutionRequest('e','s','objective',{'b':2,'a':1},'http://mcp',None,tuple(caps),schema,guard)

class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    def engine(self,store,providers,mcp):
        items=iter(providers)
        @asynccontextmanager
        async def factory(_):yield mcp
        return ExecutionEngine(store,lambda _:next(items),factory)

    async def test_empty_envelope_exposes_zero_despite_inventory(self):
        seen=[];mcp=Mcp([Capability('jobs_claim_v1','lifecycle',{})]);engine=self.engine(Store(),[ReplyProvider([ProviderReply('ok')],seen=seen)],mcp)
        outcome=await engine.execute(request());self.assertTrue(outcome.success);self.assertEqual(seen[0][1],());self.assertEqual(mcp.calls,[])

    async def test_exact_envelope_and_deterministic_source_serialization(self):
        cap=Capability('allowed','d',SCHEMA);seen=[];mcp=Mcp([cap,Capability('unrelated','x',{})]);engine=self.engine(Store(),[ReplyProvider([ProviderReply('ok')],seen=seen)],mcp)
        await engine.execute(request([cap]));self.assertEqual([t.name for t in seen[0][1]],['allowed']);self.assertEqual(seen[0][0][0]['content'],'{"input":{"a":1,"b":2},"objective":"objective"}')

    async def test_pagination_missing_and_schema_mismatch(self):
        cap=Capability('allowed','d',SCHEMA)
        pages=[[Capability('other','',{})],[cap]];out=await self.engine(Store(),[ReplyProvider([ProviderReply('ok')])],Mcp(pages=pages)).execute(request([cap]));self.assertTrue(out.success)
        out=await self.engine(Store(),[ReplyProvider([])],Mcp([])).execute(request([cap]));self.assertEqual(out.error_code,'capability_missing')
        out=await self.engine(Store(),[ReplyProvider([])],Mcp([Capability('allowed','',{})])).execute(request([cap]));self.assertEqual(out.error_code,'capability_schema_mismatch')

    async def test_more_than_128_fails_without_inventory_or_provider(self):
        caps=[Capability(f't{i}','',{}) for i in range(129)];out=await self.engine(Store(),[],Mcp()).execute(request(caps));self.assertEqual(out.error_code,'capability_limit')

    async def test_valid_dispatch_exactly_once(self):
        cap=Capability('allowed','d',SCHEMA);mcp=Mcp([cap],result={'value':7});provider=ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',{'value':2}),)),ProviderReply('done')])
        out=await self.engine(Store(),[provider],mcp).execute(request([cap]));self.assertTrue(out.success);self.assertTrue(out.mcp_effect_possible);self.assertEqual(mcp.calls,[('allowed',{'value':2})])

    async def test_source_guard_blocks_dispatch_without_mcp_effect(self):
        async def expired():raise ExecutionFailure('source_lease_lost')
        cap=Capability('allowed','d',SCHEMA);mcp=Mcp([cap]);provider=ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',{'value':2}),))])
        out=await self.engine(Store(),[provider],mcp).execute(request([cap],guard=expired));self.assertEqual(out.error_code,'source_lease_lost');self.assertFalse(out.mcp_effect_possible);self.assertEqual(mcp.calls,[])

    async def test_unknown_and_invalid_arguments_never_dispatch(self):
        cap=Capability('allowed','d',SCHEMA)
        for call in (ToolCall('c','other',{}),ToolCall('c','allowed',{'value':'bad'}),ToolCall('c','allowed','not-json')):
            mcp=Mcp([cap]);out=await self.engine(Store(),[ReplyProvider([ProviderReply(tool_calls=(call,))])],mcp).execute(request([cap]));self.assertFalse(out.success);self.assertEqual(mcp.calls,[])

    async def test_pre_dispatch_fallback_and_fresh_context(self):
        seen=[];store=Store([{'id':'m1','timeout_minutes':1},{'id':'m2','timeout_minutes':1}]);providers=[ReplyProvider(error=RuntimeError()),ReplyProvider([ProviderReply('ok')],seen=seen)]
        out=await self.engine(store,providers,Mcp()).execute(request());self.assertTrue(out.success);self.assertEqual(out.model_id,'m2');self.assertEqual(len(seen[0][0]),1);self.assertEqual(store.used,[('begin','m1'),('end','m1'),('begin','m2'),('end','m2')])

    async def test_no_fallback_after_lost_response_or_mcp_failure(self):
        cap=Capability('allowed','',SCHEMA);store=Store([{'id':'m1','timeout_minutes':1},{'id':'m2','timeout_minutes':1}]);mcp=Mcp([cap],fail=True)
        providers=[ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',{'value':1}),))]),ReplyProvider([ProviderReply('must-not-run')])]
        out=await self.engine(store,providers,mcp).execute(request([cap]));self.assertEqual(out.error_code,'mcp_failure');self.assertTrue(out.mcp_effect_possible);self.assertEqual(store.used,[('begin','m1'),('end','m1')])

    async def test_structured_results_and_fallback(self):
        store=Store([{'id':'m1','timeout_minutes':1},{'id':'m2','timeout_minutes':1}]);out=await self.engine(store,[ReplyProvider([ProviderReply('{"bad":1}')]),ReplyProvider([ProviderReply('{"value":3}')])],Mcp()).execute(request(schema=SCHEMA))
        self.assertTrue(out.success);self.assertEqual(out.result,{'value':3})

    async def test_tools_list_changed_revalidates_without_broadening(self):
        cap=Capability('allowed','',SCHEMA);mcp=Mcp([cap,Capability('new','',{})],changed=True);seen=[]
        provider=ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',{'value':1}),)),ProviderReply('ok')],seen=seen)
        out=await self.engine(Store(),[provider],mcp).execute(request([cap]));self.assertTrue(out.success);self.assertTrue(all([x.name for x in entry[1]]==['allowed'] for entry in seen))

    async def test_busy_is_immediate_and_no_queue(self):
        gate=asyncio.Event();cap=Capability('allowed','',SCHEMA);engine=self.engine(Store(),[ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',{'value':1}),)),ProviderReply('ok')])],Mcp([cap],block=gate))
        first=asyncio.create_task(engine.execute(request([cap])))
        while not engine._occupied: await asyncio.sleep(0)
        with self.assertRaises(BusyError):await engine.execute(request([cap]))
        gate.set();await first

    async def test_argument_and_result_bounds_no_truncation(self):
        cap=Capability('allowed','',{'type':'object'});huge={'x':'x'*(MAX_ARGUMENT_BYTES+1)};mcp=Mcp([cap]);out=await self.engine(Store(),[ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',huge),))])],mcp).execute(request([cap]));self.assertEqual(out.error_code,'tool_argument_limit');self.assertEqual(mcp.calls,[])
        mcp=Mcp([cap],result={'x':'x'*(MAX_TOOL_RESULT_BYTES+1)});out=await self.engine(Store(),[ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',{}),))])],mcp).execute(request([cap]));self.assertEqual(out.error_code,'tool_result_limit')

    async def test_timeout_before_dispatch_falls_back(self):
        class Slow:
            async def turn(self,*args):await asyncio.sleep(.05)
        store=Store([{'id':'m1','timeout_minutes':.0001},{'id':'m2','timeout_minutes':1}])
        out=await self.engine(store,[Slow(),ReplyProvider([ProviderReply('ok')])],Mcp()).execute(request());self.assertTrue(out.success);self.assertEqual(out.model_id,'m2')

    async def test_timeout_after_dispatch_never_falls_back(self):
        gate=asyncio.Event();cap=Capability('allowed','',SCHEMA);store=Store([{'id':'m1','timeout_minutes':.0001},{'id':'m2','timeout_minutes':1}]);mcp=Mcp([cap],block=gate)
        providers=[ReplyProvider([ProviderReply(tool_calls=(ToolCall('c','allowed',{'value':1}),))]),ReplyProvider([ProviderReply('bad fallback')])]
        out=await self.engine(store,providers,mcp).execute(request([cap]));self.assertEqual(out.error_code,'attempt_timeout');self.assertTrue(out.mcp_effect_possible);self.assertEqual(store.used,[('begin','m1'),('end','m1')])

if __name__=='__main__':unittest.main()
