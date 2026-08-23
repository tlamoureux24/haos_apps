"""Exact-certificate HTTPX transport; verification completes before HTTP writes."""
from __future__ import annotations
import hashlib,hmac,re,ssl
import httpcore,httpx

def normalize_certificate_sha256(value):
    result=re.sub(r"^sha256\s+fingerprint\s*=\s*","",str(value or "").strip(),flags=re.I).replace(":","").replace(" ","").lower()
    if result and not re.fullmatch(r"[0-9a-f]{64}",result):raise ValueError("certificate_sha256_must_contain_64_hexadecimal_characters")
    return result

class PinnedStream(httpcore.AsyncNetworkStream):
    def __init__(self,stream,expected):self.stream,self.expected=stream,expected
    async def read(self,max_bytes,timeout=None):return await self.stream.read(max_bytes,timeout)
    async def write(self,buffer,timeout=None):await self.stream.write(buffer,timeout)
    async def aclose(self):await self.stream.aclose()
    def get_extra_info(self,info):return self.stream.get_extra_info(info)
    async def start_tls(self,ssl_context,server_hostname=None,timeout=None):
        stream=await self.stream.start_tls(ssl_context,server_hostname,timeout);obj=stream.get_extra_info("ssl_object");cert=obj.getpeercert(binary_form=True) if obj else b"";actual=hashlib.sha256(cert).hexdigest()
        if not cert or not hmac.compare_digest(actual,self.expected):await stream.aclose();raise httpcore.ConnectError("certificate_sha256_mismatch")
        return PinnedStream(stream,self.expected)
class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self,expected):self.backend,self.expected=httpcore.AnyIOBackend(),expected
    async def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):return PinnedStream(await self.backend.connect_tcp(host,port,timeout,local_address,socket_options),self.expected)
    async def connect_unix_socket(self,path,timeout=None,socket_options=None):return PinnedStream(await self.backend.connect_unix_socket(path,timeout,socket_options),self.expected)
    async def sleep(self,seconds):await self.backend.sleep(seconds)
class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self,fingerprint):
        expected=normalize_certificate_sha256(fingerprint)
        if not expected:raise ValueError("certificate_sha256_required")
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE;super().__init__(verify=context,trust_env=False);self._pool=httpcore.AsyncConnectionPool(ssl_context=context,network_backend=PinnedBackend(expected))
def async_client_kwargs(fingerprint):
    value=normalize_certificate_sha256(fingerprint);return {"transport":PinnedAsyncHTTPTransport(value)} if value else {}
