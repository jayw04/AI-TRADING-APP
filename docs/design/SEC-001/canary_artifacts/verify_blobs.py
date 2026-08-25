import hashlib
EXPECT = {
 "sec/client.py":"6c1d7006f42f", "sec001_v3/fetch.py":"b19145b774d8",
 "sec001_v3/policy.py":"37ca0165b17d", "sec001_v3/spine.py":"3f37faba3861",
 "sec001_v3/decision_bytes.py":"06de91a92acc", "sec001_v3/evidence.py":"cdd61346212c",
 "sec001_v3/sections.py":"ae97502b1c9a", "sec001_v3/forbidden.py":"8570677325aa",
 "sec001_v3/__init__.py":"a50bc6c76896", "sec001_v3/driver.py":"c6f147eda499",
 "sec001_v3/state.py":"0d23793590d8",
}
NUL = bytes([0])
bad = 0
for rel, want in sorted(EXPECT.items()):
    p = "apps/backend/app/altdata/" + rel
    d = open(p, "rb").read()
    got = hashlib.sha1(b"blob " + str(len(d)).encode() + NUL + d).hexdigest()[:12]
    ok = got == want
    bad += 0 if ok else 1
    print(("PASS " if ok else "FAIL "), rel, want, got)
print("BLOB_VERIFY", "PASS" if bad == 0 else "FAIL")
