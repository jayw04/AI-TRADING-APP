#!/usr/bin/env python3
"""SEC-001 V3 Defect-F Pass 2: byte-level verification of the preserved v1.4 epoch.

READ-ONLY. Reads only from /mnt/evidence (mounted ro,norecovery).
Writes only to /root/pass2 on the investigation host's own root volume.
Never modifies, repairs, reconstructs, or deletes any evidence byte.
"""
import json, os, hashlib, time, re
from concurrent.futures import ThreadPoolExecutor

WORKERS = 24

BASE = '/mnt/evidence/opt/workbench/sec001-v3/crawl-v1.4'
RAW = os.path.join(BASE, 'raw/edgar/2026-08-24')
ART = os.path.join(RAW, 'source_decision_bytes')
MAN = os.path.join(RAW, 'source_decision_bytes.jsonl')
OUT = '/root/pass2'
NL = bytes([10])
CHUNK = 4 * 1024 * 1024

os.makedirs(OUT, exist_ok=True)
log = open(os.path.join(OUT, 'progress.log'), 'w', buffering=1)


def sha256_file(path):
    h = hashlib.sha256()
    n = 0
    with open(path, 'rb') as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


# ---------------------------------------------------------------- 1. manifest
records = []
torn = None
offset = 0
last_complete_end = 0
with open(MAN, 'rb') as fh:
    for line in fh:
        if not line.endswith(NL):
            torn = line
            break
        offset += len(line)
        last_complete_end = offset
        r = json.loads(line)
        records.append({
            'accession': r.get('accession'),
            'basename': os.path.basename(r.get('artifact_path', '')),
            'sha256': r.get('sha256'),
            'parser_body_sha256': r.get('parser_body_sha256'),
            'wire_sha256': r.get('wire_sha256'),
            'byte_length': r.get('byte_length'),
            'status': r.get('acquisition_status'),
        })

log.write('complete_records=%d torn=%s\n' % (len(records), bool(torn)))

by_path = {}
for rec in records:
    by_path.setdefault(rec['basename'], []).append(rec)
log.write('distinct_artifact_paths=%d\n' % len(by_path))

# ------------------------------------------------- 2. verify published bytes
res = {
    'checked_records': 0, 'matched_records': 0, 'mismatched_records': 0,
    'records_with_missing_file': 0,
    'files_hashed': 0, 'files_matched': 0, 'files_mismatched': 0, 'files_missing': 0,
    'bytes_hashed': 0, 'length_mismatch_records': 0,
    'parser_body_equals_artifact': 0, 'parser_body_differs': 0,
}
mismatches = []
collision_paths = {k: v for k, v in by_path.items() if len(v) > 1}
collision_verified = 0
collision_failed = 0

t0 = time.time()
names = sorted(by_path)
NLC = chr(10)


def hash_one(bn):
    fp = os.path.join(ART, bn)
    if not os.path.exists(fp):
        return bn, None, 0
    d, n = sha256_file(fp)
    return bn, d, n


digest_map = {}
done = 0
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for bn, actual, n in ex.map(hash_one, names):
        digest_map[bn] = (actual, n)
        done += 1
        if actual is not None:
            res['files_hashed'] += 1
            res['bytes_hashed'] += n
        if done % 1000 == 0:
            el = time.time() - t0
            log.write('%d/%d files %.2fGB %.1fmin %.1fMB/s' % (
                done, len(names), res['bytes_hashed'] / 1e9, el / 60,
                (res['bytes_hashed'] / 1e6) / max(el, 1)) + NLC)

log.write('HASHING DONE %.1fmin - comparing' % ((time.time() - t0) / 60) + NLC)

for bn in names:
    recs = by_path[bn]
    actual, n = digest_map[bn]
    if actual is None:
        res['files_missing'] += 1
        res['records_with_missing_file'] += len(recs)
        mismatches.append({'type': 'MISSING_FILE', 'basename': bn, 'record_count': len(recs)})
        continue
    all_ok = True
    for rec in recs:
        res['checked_records'] += 1
        if rec['sha256'] == actual:
            res['matched_records'] += 1
        else:
            res['mismatched_records'] += 1
            all_ok = False
            mismatches.append({
                'type': 'DIGEST_MISMATCH', 'basename': bn, 'accession': rec['accession'],
                'recorded_sha256': rec['sha256'], 'actual_sha256': actual,
                'recorded_byte_length': rec['byte_length'], 'actual_byte_length': n,
                'acquisition_status': rec['status'],
            })
        if rec['byte_length'] is not None and rec['byte_length'] != n:
            res['length_mismatch_records'] += 1
        if rec['parser_body_sha256'] == actual:
            res['parser_body_equals_artifact'] += 1
        else:
            res['parser_body_differs'] += 1
    if all_ok:
        res['files_matched'] += 1
    else:
        res['files_mismatched'] += 1
    if len(recs) > 1:
        if all_ok:
            collision_verified += 1
        else:
            collision_failed += 1

res['collision_paths_total'] = len(collision_paths)
res['collision_paths_verified_against_shared_digest'] = collision_verified
res['collision_paths_failed'] = collision_failed
log.write('PUBLISHED VERIFICATION DONE %.1fmin\n' % ((time.time() - t0) / 60))

# ----------------------------------------------------- 3. orphans (no records)
disk = set(os.listdir(ART))
orphan_names = sorted(disk - set(by_path))
def hash_orphan(o):
    fp = os.path.join(ART, o)
    d, n = sha256_file(fp)
    return {
        'name': o, 'kind': 'tmp' if o.endswith('.tmp') else 'bin',
        'bytes': n, 'sha256': d,
        'mtime_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(os.path.getmtime(fp))),
    }


with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    orphans = list(ex.map(hash_orphan, orphan_names))
log.write('orphans_hashed=%d\n' % len(orphans))

# --------------------------------------------------- 4. torn manifest boundary
torn_info = {'present': bool(torn)}
if torn:
    torn_info.update({
        'fragment_bytes': len(torn),
        'fragment_sha256': hashlib.sha256(torn).hexdigest(),
        'last_complete_record_end_offset': last_complete_end,
        'manifest_total_bytes': os.path.getsize(MAN),
        'trailing_bytes_after_last_complete_record': os.path.getsize(MAN) - last_complete_end,
    })
    m = re.search(rb'"accession":"([0-9-]+)"', torn)
    acc = m.group(1).decode() if m else None
    torn_info['fragment_accession'] = acc
    m2 = re.search(rb'"artifact_path":"([^"]+)"', torn)
    torn_info['fragment_artifact_path'] = m2.group(1).decode() if m2 else None
    m3 = re.search(rb'"acquisition_status":"([A-Z_]+)"', torn)
    torn_info['fragment_acquisition_status'] = m3.group(1).decode() if m3 else None
    if acc:
        cand = acc + '.bin'
        torn_info['fragment_artifact_is_orphan'] = cand in orphan_names
        torn_info['fragment_artifact_in_manifest'] = cand in by_path
        cp = os.path.join(ART, cand)
        if os.path.exists(cp):
            d, n = sha256_file(cp)
            torn_info['fragment_artifact_actual_sha256'] = d
            torn_info['fragment_artifact_actual_bytes'] = n
        else:
            torn_info['fragment_artifact_exists'] = False
    # verifiable digest over the complete-record prefix only
    h = hashlib.sha256()
    remaining = last_complete_end
    with open(MAN, 'rb') as fh:
        while remaining > 0:
            b = fh.read(min(CHUNK, remaining))
            if not b:
                break
            h.update(b)
            remaining -= len(b)
    torn_info['complete_prefix_sha256'] = h.hexdigest()

# ------------------------------------------------------- 5. byte-class census
def tree_bytes(path):
    total = 0
    count = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                count += 1
            except OSError:
                pass
    return total, count


published_bytes = 0
for bn in by_path:
    p = os.path.join(ART, bn)
    try:
        published_bytes += os.path.getsize(p)
    except OSError:
        pass
orphan_bin_bytes = sum(o['bytes'] for o in orphans if o['kind'] == 'bin')
orphan_tmp_bytes = sum(o['bytes'] for o in orphans if o['kind'] == 'tmp')
obs_bytes, obs_count = tree_bytes(os.path.join(RAW, 'observations'))
build_bytes, build_count = tree_bytes(os.path.join(BASE, 'build'))
state_bytes, state_count = tree_bytes(os.path.join(BASE, 'state'))
manifest_bytes = os.path.getsize(MAN)
control_bytes = 0
for f in ('runner.log', 'runner_progress.jsonl', 'RUNNER.pid', 'RUNNER_STOPPED.json'):
    fp = os.path.join(BASE, f)
    if os.path.exists(fp):
        control_bytes += os.path.getsize(fp)

classes = {
    'published_decision_artifacts': {'bytes': published_bytes, 'files': len(by_path)},
    'orphan_finalized_artifacts': {'bytes': orphan_bin_bytes,
                                   'files': sum(1 for o in orphans if o['kind'] == 'bin')},
    'temporary_artifacts_tmp': {'bytes': orphan_tmp_bytes,
                                'files': sum(1 for o in orphans if o['kind'] == 'tmp')},
    'decision_byte_manifest': {'bytes': manifest_bytes, 'files': 1},
    'observations': {'bytes': obs_bytes, 'files': obs_count},
    'build_segments': {'bytes': build_bytes, 'files': build_count},
    'crawl_state': {'bytes': state_bytes, 'files': state_count},
    'runner_control_and_logs': {'bytes': control_bytes, 'files': 4},
}
classes['TOTAL_accounted'] = {
    'bytes': sum(v['bytes'] for v in classes.values()),
    'files': sum(v['files'] for v in classes.values()),
}

report = {
    'pass': 2,
    'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'source': 'read-only snapshot-derived copy at /mnt/evidence',
    'verification': res,
    'byte_classes': classes,
    'torn_manifest_boundary': torn_info,
    'orphans': orphans,
    'mismatch_count': len(mismatches),
}
with open(os.path.join(OUT, 'pass2_report.json'), 'w') as f:
    json.dump(report, f, indent=2, sort_keys=True)
with open(os.path.join(OUT, 'mismatches.jsonl'), 'w') as f:
    for m in mismatches:
        f.write(json.dumps(m, sort_keys=True) + '\n')

log.write('DONE total %.1f min\n' % ((time.time() - t0) / 60))
log.write('checked=%d matched=%d mismatched=%d missing_files=%d\n'
          % (res['checked_records'], res['matched_records'],
             res['mismatched_records'], res['files_missing']))
log.close()
print('PASS2_COMPLETE')
