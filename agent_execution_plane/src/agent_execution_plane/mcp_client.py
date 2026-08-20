"""Official MCP SDK Streamable HTTP execution session."""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agent_execution_plane.execution import Capability, ExecutionRequest


class StreamableMcpSession:
    def __init__(self, request: ExecutionRequest): self.request=request; self.stack=AsyncExitStack(); self.session=None; self._changed=False
    async def __aenter__(self):
        headers={'Authorization':f'Bearer {self.request.mcp_bearer_token}'} if self.request.mcp_bearer_token else {}
        client=await self.stack.enter_async_context(httpx.AsyncClient(headers=headers,follow_redirects=False))
        read,write,_=await self.stack.enter_async_context(streamable_http_client(self.request.mcp_url,http_client=client))
        async def observe(message):
            root=getattr(getattr(message,'message',None),'root',None)
            if getattr(root,'method',None)=='notifications/tools/list_changed': self._changed=True
        self.session=await self.stack.enter_async_context(ClientSession(read,write,message_handler=observe)); await self.session.initialize(); return self
    async def __aexit__(self,*args): await self.stack.aclose()
    async def list_tools(self,cursor=None):
        result=await self.session.list_tools(cursor=cursor)
        tools=[Capability(t.name,t.description or '',dict(t.inputSchema)) for t in result.tools]
        return tools,result.nextCursor
    async def call_tool(self,name,arguments):
        result=await self.session.call_tool(name,arguments=arguments)
        if getattr(result,'isError',False): raise RuntimeError('mcp_tool_error')
        structured=getattr(result,'structuredContent',None)
        if structured is not None:return structured
        output=[]
        for item in result.content:
            if getattr(item,'type',None)=='text':
                try: output.append(json.loads(item.text))
                except json.JSONDecodeError: output.append(item.text)
            else: output.append(item.model_dump(mode='json'))
        return output[0] if len(output)==1 else output
    async def changed(self):
        value,self._changed=self._changed,False; return value


def session_factory(request: ExecutionRequest): return StreamableMcpSession(request)
