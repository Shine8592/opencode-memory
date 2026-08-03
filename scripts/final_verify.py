"""Final comprehensive verification after all upgrades."""
import subprocess, json, sys, time, os
from pathlib import Path

SERVER = str(Path(__file__).parent / "mcp_server.py")
CWD = str(Path(__file__).parent.parent.parent)  # project root

def say(text):
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()

def run(requests, timeout=60):
    stdin_data = "\n".join(requests) + "\n"
    proc = subprocess.Popen(
        ["python", "-u", SERVER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, cwd=CWD,
    )
    stdout, stderr = proc.communicate(input=stdin_data.encode("utf-8"), timeout=timeout)
    out = stdout.decode("utf-8", errors="replace")
    return [json.loads(l) for l in out.strip().split("\n") if l.strip()]

def get_result(responses):
    for r in reversed(responses):
        if "result" in r:
            return r["result"]
    return None

def has_content(responses, keyword):
    result = get_result(responses)
    if not result:
        return False
    texts = [c["text"] for c in result.get("content", [])]
    combined = " ".join(texts)
    return keyword in combined

passed = 0
failed = 0

def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        say(f"  [PASS] {name}" + (f"  {detail}" if detail else ""))
    else:
        failed += 1
        say(f"  [FAIL] {name}" + (f"  {detail}" if detail else ""))

say("=" * 50)
say("Final Verification: MCP Memory System")
say("=" * 50)

# === 1. Protocol & Cold Start ===
say("\n-- 1. Protocol & Cold Start --")
t0 = time.time()
resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}',
], timeout=60)
cold_start = time.time() - t0
check("Cold start", cold_start < 5, f"{cold_start:.1f}s")
check("Init response", len(resp) >= 2 and "result" in resp[0])
tools = resp[1]["result"]["tools"] if len(resp) >= 2 and "result" in resp[1] else []
check("Tools listed (>=12)", len(tools) >= 12, f"{len(tools)} tools")

# === 2. Status ===
say("\n-- 2. Memory Status --")
resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_status","arguments":{}}}',
], timeout=30)
check("Status response", len(resp) >= 2 and "result" in resp[-1])
if len(resp) >= 2 and "result" in resp[-1]:
    text = resp[-1]["result"]["content"][0]["text"]
    say(f"  Project: {text.split(chr(10))[1].strip()}")
    say(f"  Index: {'EXISTS' if '存在' in text else 'MISSING'}")
    say(f"  STM: {[l for l in text.split(chr(10)) if '短期记忆' in l][0] if '短期记忆' in text else '?'}")

# === 3. Auto Remember + Auto Recall (key test) ===
say("\n-- 3. Auto Remember + Auto Recall (no reindex) --")
unique_id = f"auto_test_{int(time.time())}"
resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    f'{{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{{"name":"memory_remember","arguments":{{"content":"[auto] {unique_id}","tags":"verify"}}}}}}',
], timeout=60)
check("Remember new memory", len(resp) >= 2 and "result" in resp[-1])

# Recall immediately (separate process, no reindex)
resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    f'{{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{{"name":"memory_recall","arguments":{{"query":"{unique_id}","top_k":5}}}}}}',
], timeout=60)
found = has_content(resp, unique_id)
check("Recall without reindex", found, f"query='{unique_id}' {'FOUND' if found else 'NOT FOUND'}")

# === 4. All Other Tools ===
say("\n-- 4. Other Tools --")

# Status (already tested above)
resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_forget","arguments":{"keyword":"auto_test_99999"}}}',
], timeout=60)
check("Forget (no-op)", len(resp) >= 2 and "result" in resp[-1])

resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_reindex","arguments":{"background":true}}}',
], timeout=60)
check("Reindex (background)", len(resp) >= 2 and "result" in resp[-1])

resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_history","arguments":{"limit":3}}}',
], timeout=60)
check("History", len(resp) >= 2 and "result" in resp[-1])

# === 5. Error Handling ===
say("\n-- 5. Error Handling --")
resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_recall","arguments":{"query":"","top_k":3}}}',
], timeout=60)
check("Empty query handled", len(resp) >= 2 and "result" in resp[-1])

resp = run([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_nonexistent","arguments":{}}}',
], timeout=60)
check("Unknown tool returns error", len(resp) >= 2 and "error" in resp[-1])

# === 6. Model Integrity ===
say("\n-- 6. Model Check --")
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).parent))
from memory_config import MODEL_PATH
model_path = MODEL_PATH
check("Model path exists", model_path.exists(), str(model_path))
if model_path.exists():
    from sentence_transformers import SentenceTransformer
    t0 = time.time()
    m = SentenceTransformer(str(model_path))
    load_time = time.time() - t0
    check("Model loads", m is not None, f"{load_time:.1f}s")
    check("Dimension 384", m.get_embedding_dimension() == 384)
    
    t0 = time.time()
    v = m.encode("Hello world", normalize_embeddings=True)
    enc_time = time.time() - t0
    check("Encode works", len(v) == 384, f"{enc_time:.3f}s")
    
    v2 = m.encode("Hello world", normalize_embeddings=True)
    check("Deterministic", float(abs(v - v2).max()) < 1e-6)
    
    # Semantic sanity
    a = m.encode("dog", normalize_embeddings=True)
    b = m.encode("puppy", normalize_embeddings=True)
    c = m.encode("car", normalize_embeddings=True)
    check("dog~puppy > dog~car", float(a @ b) > float(a @ c),
          f"dog-puppy={float(a@b):.3f} dog-car={float(a@c):.3f}")

# === Summary ===
say("\n" + "=" * 50)
say(f"Results: {passed} passed, {failed} failed out of {passed + failed} checks")
if failed == 0:
    say("ALL CHECKS PASSED - System fully operational")
else:
    say("SOME CHECKS FAILED - Review above")
say("=" * 50)
