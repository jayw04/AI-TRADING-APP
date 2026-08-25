import hashlib, inspect, sys
import httpx, httpcore
from httpcore._sync.http11 import HTTP11Connection as C
p = inspect.getsourcefile(C)
d = open(p, "rb").read()
sha = hashlib.sha256(d).hexdigest()
print("httpx          ", httpx.__version__)
print("httpcore       ", httpcore.__version__)
print("READ_NUM_BYTES ", C.READ_NUM_BYTES)
print("http11_sha256  ", sha)
ok = (httpx.__version__ == "0.28.1"
      and httpcore.__version__ == "1.0.9"
      and C.READ_NUM_BYTES == 65536
      and sha == "f644ff92a0a10822544c7c30db866647f7b371d6e94585a4b03fa060dce464ff")
print("DEPENDENCY_GATE", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
